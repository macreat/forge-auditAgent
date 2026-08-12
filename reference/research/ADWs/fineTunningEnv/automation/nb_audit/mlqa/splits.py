"""Runtime split checks: partition disjointness and reproducibility.

Operating on the executed namespace (``ctx``) plus the notebook IR, this check
discovers split-like variables — ``train_ids`` / ``val_ids`` / ``test_ids``,
``X_train``/``X_test``/``y_test`` (``train_test_split`` outputs), and
``train_set``/``val_set``/``test_set`` (``torch.utils.data.Subset``) — and asserts
the critical §6.3 invariant::

    TRAIN ∩ VALIDATION = ∅
    TRAIN ∩ TEST       = ∅
    VALIDATION ∩ TEST  = ∅

Overlap is a severity-9 experimental-validity problem (data leakage between
splits). A randomized split detected in the IR without any seed / ``random_state``
evidence in the namespace is reported as a severity-8 reproducibility finding.

Heuristics are deliberately conservative to avoid false positives:

- only variables named like a split partition (train/val/test role) are paired;
- 1-D values are only compared when the name looks like sample *identifiers*
  (``*_ids``, ``*_indices``, ``*_idx``, ``*_subset``), because raw label arrays
  naturally share values across splits;
- 2-D values (feature matrices) are compared row-wise, since identical rows are
  duplicate samples.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from nb_audit.ir import NotebookModel
from nb_audit.models import Finding, Location
from nb_audit.mlqa.check_registry import RuntimeCheck

# --------------------------------------------------------------------------- #
# Role classification tables
# --------------------------------------------------------------------------- #
_TRAIN_SUFFIXES = ("_train",)
_VAL_SUFFIXES = ("_val", "_valid", "_validation", "_dev")
_TEST_SUFFIXES = ("_test",)

_TRAIN_PREFIXES = ("train_",)
_VAL_PREFIXES = ("val_", "valid_", "validation_", "dev_")
_TEST_PREFIXES = ("test_",)

_ROLES = ("train", "val", "test")

# Names that mark a variable as sample identifiers (for 1-D comparison).
_ID_SUFFIXES = (
    "ids", "id", "idx", "indices", "indexes", "index",
    "samples", "sample", "subset",
)

_RANDOMIZED_SPLITS = frozenset({
    "train_test_split", "ShuffleSplit", "StratifiedShuffleSplit",
    "KFold", "StratifiedKFold", "random_split", "GroupShuffleSplit",
    "RepeatedKFold", "RepeatedStratifiedKFold",
})

_PAIR_LABELS = {
    ("train", "val"): "TRAIN ∩ VALIDATION",
    ("train", "test"): "TRAIN ∩ TEST",
    ("val", "test"): "VALIDATION ∩ TEST",
}


# --------------------------------------------------------------------------- #
# Value normalization
# --------------------------------------------------------------------------- #
def _flat(obj) -> Iterable:
    """Return a flat iterable of the object's elements (best-effort)."""
    if hasattr(obj, "reshape") and hasattr(obj, "tolist"):  # numpy / torch
        return obj.reshape(-1).tolist()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, (list, tuple, set, frozenset, range)):
        return list(obj)
    if hasattr(obj, "indices") and not callable(getattr(obj, "indices", None)):
        return _flat(obj.indices)
    return [obj]


def _to_hashable(item):
    if isinstance(item, (list, tuple)):
        return tuple(_to_hashable(x) for x in item)
    if hasattr(item, "item") and hasattr(item, "dtype"):  # numpy scalar
        return item.item()
    try:
        hash(item)
        return item
    except TypeError:
        return str(item)


def _hashable_set(items: Iterable) -> set:
    return {_to_hashable(it) for it in items}


def _looks_like_ids(name: str) -> bool:
    return name.lower().endswith(_ID_SUFFIXES)


def _to_id_set(obj, name: str) -> set | None:
    """Return a set of hashable sample ids, or ``None`` when not identity-like."""
    # 1) torch Subset-like: explicit sample indices.
    if hasattr(obj, "indices") and not callable(getattr(obj, "indices", None)):
        return _hashable_set(_flat(obj.indices))

    # 2) pandas DataFrame → rows are samples.
    if hasattr(obj, "columns") and hasattr(obj, "values"):
        return _hashable_set(tuple(r) for r in obj.values.tolist())

    # 3) pandas Series → flat values (ids only).
    if hasattr(obj, "values") and hasattr(obj, "to_list"):
        return _hashable_set(obj.to_list()) if _looks_like_ids(name) else None

    # 4) array/tensor-like with shape.
    if hasattr(obj, "shape") and hasattr(obj, "tolist"):
        ndim = len(obj.shape)
        if ndim >= 2:
            return _hashable_set(tuple(r) for r in obj.tolist())
        if _looks_like_ids(name):
            return _hashable_set(obj.tolist())
        return None

    # 5) plain Python sequences.
    seq = list(obj) if isinstance(obj, (set, frozenset, range)) else obj
    if not isinstance(seq, (list, tuple)):
        return None
    if seq and isinstance(seq[0], (list, tuple)):
        return _hashable_set(tuple(r) for r in seq)
    if _looks_like_ids(name):
        return _hashable_set(seq)
    return None


# --------------------------------------------------------------------------- #
# Split discovery
# --------------------------------------------------------------------------- #
def _role_of(name: str) -> str | None:
    low = name.lower()
    for marker in _TRAIN_SUFFIXES:
        if low.endswith(marker):
            return "train"
    for marker in _VAL_SUFFIXES:
        if low.endswith(marker):
            return "val"
    for marker in _TEST_SUFFIXES:
        if low.endswith(marker):
            return "test"
    for marker in _TRAIN_PREFIXES:
        if low.startswith(marker):
            return "train"
    for marker in _VAL_PREFIXES:
        if low.startswith(marker):
            return "val"
    for marker in _TEST_PREFIXES:
        if low.startswith(marker):
            return "test"
    return None


def _base_of(name: str, role: str) -> str:
    """Strip the role marker from ``name`` to recover its base (grouping key)."""
    low = name.lower()
    suffix_map = {
        "train": _TRAIN_SUFFIXES,
        "val": _VAL_SUFFIXES,
        "test": _TEST_SUFFIXES,
    }
    for marker in suffix_map[role]:
        if low.endswith(marker):
            return name[: -len(marker)]
    prefix_map = {
        "train": _TRAIN_PREFIXES,
        "val": _VAL_PREFIXES,
        "test": _TEST_PREFIXES,
    }
    for marker in prefix_map[role]:
        if low.startswith(marker):
            return name[len(marker):]
    return name


def _discover_groups(ctx: Mapping) -> dict[str, dict[str, tuple[str, object]]]:
    """Group split-named variables by base name → role → (key, value).

    Only variables with a recognizable train/val/test role participate. Returns
    groups keyed by base name, each mapping role → ``(original_key, value)``.
    Groups with fewer than two distinct roles are discarded.
    """
    groups: dict[str, dict[str, tuple[str, object]]] = {}
    for key, value in ctx.items():
        role = _role_of(str(key))
        if role is None:
            continue
        base = _base_of(str(key), role)
        groups.setdefault(base, {})[role] = (str(key), value)

    return {base: roles for base, roles in groups.items() if len(roles) >= 2}


def _seed_present(ctx: Mapping) -> bool:
    for key in ctx:
        low = str(key).lower()
        if "seed" in low or "random_state" in low:
            return True
    return False


def _has_randomized_split(model: NotebookModel) -> bool:
    for split in model.splits:
        dotted = split.name or ""
        if dotted.rsplit(".", 1)[-1] in _RANDOMIZED_SPLITS:
            return True
    return False


def _split_cell(model: NotebookModel) -> str:
    for split in model.splits:
        if split.cell_id:
            return split.cell_id
    return ""


# --------------------------------------------------------------------------- #
# The check
# --------------------------------------------------------------------------- #
class SplitCheck(RuntimeCheck):
    """Split disjointness (data leakage) and reproducibility checks."""

    name = "splits"
    category = "splits"
    severity = 9

    def check(self, model: NotebookModel, ctx: Mapping) -> list[Finding]:
        findings: list[Finding] = []
        cell = _split_cell(model)

        groups = _discover_groups(ctx)
        for base in sorted(groups):
            roles = groups[base]
            keys = {role: key for role, (key, _value) in roles.items()}
            id_sets = {
                role: _to_id_set(value, key)
                for role, (key, value) in roles.items()
            }
            for (role_a, role_b), label in _PAIR_LABELS.items():
                set_a = id_sets.get(role_a)
                set_b = id_sets.get(role_b)
                if set_a is None or set_b is None:
                    continue
                overlap = set_a & set_b
                if not overlap:
                    continue
                findings.append(
                    self.finding(
                        location=Location(cell=cell),
                        issue=(
                            f"Data leakage: {label} overlap of {len(overlap)} "
                            f"sample(s) between split '{keys[role_a]}' "
                            f"and '{keys[role_b]}'"
                        ),
                        root_cause=(
                            "Train/validation/test partitions are not disjoint — "
                            "the same samples appear in more than one split"
                        ),
                        impact=(
                            "Reported metrics are optimistically biased; the model "
                            "is evaluated on data it was trained or selected on"
                        ),
                        correction=(
                            "Re-derive the splits so each sample belongs to exactly "
                            "one partition (e.g. unique indices, no shared rows)"
                        ),
                        severity=9,
                        category="splits",
                    )
                )

        # Reproducibility: randomized split without seed/random_state evidence.
        if groups and _has_randomized_split(model) and not _seed_present(ctx):
            findings.append(
                self.finding(
                    location=Location(cell=cell),
                    issue="Randomized data split detected with no seed or random_state",
                    root_cause=(
                        "A randomized split (train_test_split, KFold, ShuffleSplit, "
                        "random_split, ...) is defined but no seed / random_state is "
                        "present in the executed namespace"
                    ),
                    impact="Partitions differ between runs; results are not reproducible",
                    correction="Fix the split with a seed (random_state=...) or a global seed",
                    severity=8,
                    category="reproducibility",
                )
            )

        return findings
