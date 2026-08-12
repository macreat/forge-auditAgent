"""Runtime artifact provenance checks (§6.11, §6.15).

Operating on the notebook IR plus the executed namespace (``ctx``), this check
validates that every declared artifact (checkpoint / plot / CSV / JSON write)
has a matching value in the namespace, and that the value's *kind* matches the
declared artifact type:

- **missing** — an artifact the notebook writes (with a path) has no
  corresponding variable in the executed namespace (severity 8);
- **mismatch** — a namespace value backing a declared artifact is of the wrong
  kind (e.g. a scalar where a CSV table was declared, a plain dict where a plot
  figure was expected) (severity 8).

Provenance is asserted deterministically and without an LLM: an artifact is
"declared" from the IR's artifact write calls (with their extracted path), and
"expected" by matching the path stem against namespace variable names. Duck-
typed kind checks keep it framework-agnostic (pandas DataFrames, matplotlib
figures, NumPy arrays, plain dicts/lists).
"""

from __future__ import annotations

from typing import Mapping

from nb_audit.ir import NotebookModel
from nb_audit.models import Finding, Location
from nb_audit.mlqa.check_registry import RuntimeCheck

# Extension → kind classification.
_PLOT_EXTS = {"png", "jpg", "jpeg", "pdf", "svg", "tif", "tiff", "gif"}
_CSV_EXTS = {"csv", "tsv", "txt"}
_JSON_EXTS = {"json"}
_BINARY_EXTS = {
    "pt", "pth", "ckpt", "bin", "safetensors", "weights", "pkl", "pickle",
    "npy", "npz",
}

# Call-name → kind classification (writer call names captured by the IR).
_PLOT_WRITERS = {"savefig"}
_CSV_WRITERS = {"to_csv", "savetxt"}
_JSON_WRITERS = {"to_json"}
_BINARY_WRITERS = {"save", "dump", "savez", "savez_compressed", "to_pickle"}


def _extension(path: str) -> str:
    if "." not in path:
        return ""
    return path.rsplit(".", 1)[-1].lower()


def _kind(path: str, writer: str) -> str:
    """Classify a declared artifact as ``plot`` / ``csv`` / ``json`` / ``binary``."""
    ext = _extension(path)
    if ext in _PLOT_EXTS or writer in _PLOT_WRITERS:
        return "plot"
    if ext in _CSV_EXTS or writer in _CSV_WRITERS:
        return "csv"
    if ext in _JSON_EXTS or writer in _JSON_WRITERS:
        return "json"
    if ext in _BINARY_EXTS or writer in _BINARY_WRITERS:
        return "binary"
    return "other"


def _stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if "." in name:
        return name.rsplit(".", 1)[0]
    return name


def _describe(obj) -> str:
    """Stable, human-readable type description for a mismatch finding."""
    if callable(getattr(obj, "savefig", None)):
        return "figure"
    if isinstance(obj, Mapping):
        return "dict"
    if isinstance(obj, (list, tuple)):
        return "list"
    if isinstance(obj, str):
        return "str"
    if isinstance(obj, bool):
        return "bool"
    if isinstance(obj, (int, float)):
        return "scalar"
    if hasattr(obj, "shape"):
        try:
            return f"array/tensor(shape={list(obj.shape)})"
        except Exception:  # pragma: no cover - defensive
            return "array/tensor"
    return type(obj).__name__


# -- kind validators (duck-typed) -------------------------------------------- #
def _is_figure(obj) -> bool:
    return callable(getattr(obj, "savefig", None))


def _is_numeric_array(obj) -> bool:
    if hasattr(obj, "shape") and hasattr(obj, "tolist"):
        try:
            return len(obj.shape) >= 1
        except Exception:  # pragma: no cover - defensive
            return False
    return False


def _is_tabular(obj) -> bool:
    if hasattr(obj, "columns") and hasattr(obj, "values"):
        return True
    if isinstance(obj, (list, tuple)):
        return bool(obj) and all(isinstance(r, (list, tuple, Mapping)) for r in obj)
    return False


def _is_json_like(obj) -> bool:
    if obj is None or isinstance(obj, (Mapping, list, tuple, str, int, float, bool)):
        return True
    if hasattr(obj, "item") and callable(obj.item) and hasattr(obj, "shape"):
        try:
            return len(obj.shape) == 0  # 0-d scalar
        except Exception:  # pragma: no cover - defensive
            return False
    return False


def _is_state_like(obj) -> bool:
    if isinstance(obj, Mapping):
        return True
    return callable(getattr(obj, "state_dict", None))


def _matches_kind(kind: str, obj) -> bool:
    if kind == "plot":
        return _is_figure(obj) or _is_numeric_array(obj)
    if kind == "csv":
        return _is_tabular(obj)
    if kind == "json":
        return _is_json_like(obj) and not _is_figure(obj)
    if kind == "binary":
        return _is_state_like(obj)
    return True  # "other" — no invariant to assert


def _candidate_keys(ctx: Mapping, stem: str) -> list[str]:
    """Namespace keys whose name matches an artifact path stem (deterministic)."""
    stem_l = stem.lower()
    exact = [str(k) for k in ctx if str(k).lower() == stem_l]
    if exact:
        return [exact[0]]
    return sorted(str(k) for k in ctx if stem_l in str(k).lower())


class ArtifactsCheck(RuntimeCheck):
    """Provenance checks for checkpoint/plot/csv/json artifacts."""

    name = "artifacts"
    category = "artifacts"
    severity = 8

    def check(self, model: NotebookModel, ctx: Mapping) -> list[Finding]:
        findings: list[Finding] = []

        for artifact in model.artifacts:
            path = artifact.path or ""
            if not path:
                continue
            kind = _kind(path, artifact.name)
            if kind == "other":
                continue

            candidates = _candidate_keys(ctx, _stem(path))
            location = Location(cell=artifact.cell_id, line=artifact.line)

            if not candidates:
                findings.append(
                    self.finding(
                        location=location,
                        issue=(
                            f"Artifact '{path}' ({kind}) is declared but has no "
                            "matching value in the executed namespace"
                        ),
                        root_cause=(
                            "The notebook writes an artifact but the variable that "
                            "should hold its content is absent after execution"
                        ),
                        impact=(
                            "The reported artifact cannot be reproduced or audited; "
                            "its provenance is unverifiable"
                        ),
                        correction=(
                            "Ensure the variable producing the artifact is computed "
                            "before the write call, or fix the artifact path"
                        ),
                        severity=8,
                        category="artifacts",
                    )
                )
                continue

            value = ctx[candidates[0]]
            if _matches_kind(kind, value):
                continue

            findings.append(
                self.finding(
                    location=location,
                    issue=(
                        f"Artifact '{path}' ({kind}) mismatched: namespace "
                        f"'{candidates[0]}' is a {_describe(value)}"
                    ),
                    root_cause=(
                        "The value backing the declared artifact is of the wrong "
                        "type for the artifact's declared format"
                    ),
                    impact=(
                        "The saved artifact does not represent the intended "
                        "experiment output; downstream consumers get wrong data"
                    ),
                    correction=(
                        "Write the correct object for the artifact format (e.g. a "
                        "table for CSV, a dict/list for JSON, a figure for a plot)"
                    ),
                    severity=8,
                    category="artifacts",
                )
            )

        return findings
