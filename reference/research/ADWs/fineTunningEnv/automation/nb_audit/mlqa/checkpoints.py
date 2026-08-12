"""Runtime checkpoint checks (§6.6, §6.7): restoration + architecture/loss compatibility.

After execution, the notebook IR plus the executed namespace (``ctx``) is enough
to assert the deterministic checkpoint invariants that static analysis cannot:

- **restoration** — the notebook saves or claims to load a checkpoint, but no
  checkpoint object exists in the executed namespace (the "best checkpoint is
  not restored" failure, §6.7). Severity 9.
- **architecture compatibility** — a restored checkpoint's state-dict keys must
  match the model's ``state_dict`` keys (§6.2). Severity 9.
- **loss/value compatibility** — any loss / best-metric scalar recorded inside a
  checkpoint must be finite. Severity 8.

All detection is duck-typed (``Mapping`` state dicts, ``state_dict()`` methods,
source-text signals) so it works with PyTorch, scikit-learn, and lightweight
test doubles alike. Detection is name-driven and order-independent so repeated
runs over the same namespace are byte-identical.
"""

from __future__ import annotations

import math
from typing import Mapping

from nb_audit.ir import NotebookModel
from nb_audit.models import Finding, Location
from nb_audit.mlqa.check_registry import RuntimeCheck

# Source-text signals (matched against code cell source).
_SAVE_SIGNALS = ("torch.save", "save_pretrained", "save_checkpoint", "save_weights")
_LOAD_SIGNALS = (
    "torch.load", "load_state_dict", "load_checkpoint", "load_weights",
    "from_pretrained",
)

# Names that mark a variable as checkpoint-like / model-like.
_CHECKPOINT_HINTS = ("checkpoint", "ckpt", "state_dict", "weights", "state", "best")
_MODEL_HINTS = (
    "model", "net", "module", "network", "encoder", "decoder", "backbone",
    "classifier", "estimator",
)

# Checkpoint artifact extensions used to recognize a saved checkpoint in the IR.
_CHECKPOINT_EXTS = (
    ".pt", ".pth", ".ckpt", ".bin", ".safetensors", ".weights", ".onnx",
)

# Keys a full checkpoint dict may wrap the actual state dict under.
_STATE_WRAPPER_KEYS = (
    "model_state_dict", "state_dict", "model_state", "model", "weights",
    "net", "module",
)

# Scalar loss / selection keys a checkpoint may record.
_LOSS_KEYS = (
    "loss", "best_loss", "val_loss", "train_loss", "test_loss",
    "best_score", "best_metric", "best_accuracy", "best_f1", "best_auc",
)


def _is_mapping(obj) -> bool:
    return isinstance(obj, Mapping)


def _keys(obj) -> set[str] | None:
    """Return the state-dict-style key set of ``obj``, or ``None``."""
    if _is_mapping(obj):
        return {str(k) for k in obj}
    state_dict = getattr(obj, "state_dict", None)
    if callable(state_dict):
        try:
            result = state_dict()
            if _is_mapping(result):
                return {str(k) for k in result}
        except Exception:  # pragma: no cover - defensive duck-typing
            return None
    keys = getattr(obj, "keys", None)
    if callable(keys):
        try:
            return {str(k) for k in keys()}
        except Exception:  # pragma: no cover - defensive duck-typing
            return None
    return None


def _checkpoint_objs(ctx: Mapping) -> dict[str, object]:
    """Discover checkpoint-like objects (state dicts / checkpoint vars)."""
    result: dict[str, object] = {}
    for key, value in ctx.items():
        low = str(key).lower()
        if not any(hint in low for hint in _CHECKPOINT_HINTS):
            continue
        if _is_mapping(value) or callable(getattr(value, "state_dict", None)):
            result[str(key)] = value
    return result


def _model_objs(ctx: Mapping) -> dict[str, object]:
    """Discover model-like objects (non-mapping objects with a ``state_dict``)."""
    result: dict[str, object] = {}
    for key, value in ctx.items():
        if _is_mapping(value):
            continue
        if not callable(getattr(value, "state_dict", None)):
            continue
        low = str(key).lower()
        if any(hint in low for hint in _MODEL_HINTS) or hasattr(value, "parameters"):
            result[str(key)] = value
    return result


def _model_keys_from_checkpoint(checkpoint) -> set[str] | None:
    """Unwrap a full checkpoint dict down to the model's state-dict keys."""
    if _is_mapping(checkpoint):
        for wrapper in _STATE_WRAPPER_KEYS:
            if wrapper in checkpoint:
                inner = _keys(checkpoint[wrapper])
                if inner:
                    return inner
    return _keys(checkpoint)


def _finite(value) -> bool:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return True  # non-numeric recorded values are out of scope
    return not (math.isnan(numeric) or math.isinf(numeric))


def _save_declared(model: NotebookModel) -> bool:
    for cell in model.code_cells:
        source = cell.source
        if any(signal in source for signal in _SAVE_SIGNALS):
            return True
        if "state_dict()" in source:  # model.state_dict() being serialized
            return True
    for artifact in model.artifacts:
        path = (artifact.path or "").lower()
        if path.endswith(_CHECKPOINT_EXTS):
            return True
    return False


def _load_declared(model: NotebookModel) -> bool:
    return any(
        any(signal in cell.source for signal in _LOAD_SIGNALS)
        for cell in model.code_cells
    )


def _checkpoint_cell(model: NotebookModel) -> str:
    for cell in model.code_cells:
        if "checkpoint" in cell.source or "state_dict" in cell.source:
            return cell.id
    for artifact in model.artifacts:
        if (artifact.path or "").lower().endswith(_CHECKPOINT_EXTS):
            return artifact.cell_id
    return ""


class CheckpointsCheck(RuntimeCheck):
    """Checkpoint restoration and architecture/loss compatibility checks."""

    name = "checkpoints"
    category = "checkpoints"
    severity = 9

    def check(self, model: NotebookModel, ctx: Mapping) -> list[Finding]:
        findings: list[Finding] = []
        cell = _checkpoint_cell(model)

        save_declared = _save_declared(model)
        load_declared = _load_declared(model)
        checkpoints = _checkpoint_objs(ctx)
        models = _model_objs(ctx)

        # 1) restoration — a save/load is claimed but no checkpoint survived.
        if (save_declared or load_declared) and not checkpoints:
            if load_declared and not save_declared:
                issue = (
                    "Checkpoint restoration claimed (load_state_dict/torch.load) "
                    "but no checkpoint object is present in the executed namespace"
                )
            elif save_declared and not load_declared:
                issue = (
                    "Checkpoint saved but never restored: the best checkpoint is "
                    "not loaded back before final evaluation"
                )
            else:
                issue = (
                    "Checkpoint save/load detected but no checkpoint object is "
                    "present in the executed namespace"
                )
            findings.append(
                self.finding(
                    location=Location(cell=cell),
                    issue=issue,
                    root_cause=(
                        "The notebook claims to save/restore a checkpoint, but no "
                        "checkpoint/state-dict object exists in the executed "
                        "namespace — the selected model was never restored"
                    ),
                    impact=(
                        "Final evaluation runs on a model that was not selected/"
                        "restored, so reported results do not reflect the saved "
                        "best checkpoint"
                    ),
                    correction=(
                        "Load the saved checkpoint and apply it to the model "
                        "(e.g. model.load_state_dict(torch.load(path))) before "
                        "final evaluation"
                    ),
                    severity=9,
                    category="checkpoints",
                )
            )

        # 2) architecture compatibility — restored state keys must match the model.
        for model_key in sorted(models):
            model_keys = _keys(models[model_key])
            if model_keys is None:
                continue
            for checkpoint_key in sorted(checkpoints):
                checkpoint_keys = _model_keys_from_checkpoint(checkpoints[checkpoint_key])
                if checkpoint_keys is None:
                    continue
                if model_keys == checkpoint_keys:
                    continue
                findings.append(
                    self.finding(
                        location=Location(cell=cell),
                        issue=(
                            f"Checkpoint architecture mismatch: model "
                            f"'{model_key}' and checkpoint '{checkpoint_key}' have "
                            "different state-dict keys"
                        ),
                        root_cause=(
                            "The restored checkpoint's parameter names do not match "
                            "the model's architecture — the checkpoint was trained "
                            "with a different model definition"
                        ),
                        impact=(
                            "Restoring the checkpoint is impossible or silently "
                            "mis-loads weights; the evaluated model is wrong"
                        ),
                        correction=(
                            "Restore the checkpoint into a model with the same "
                            "architecture (same layer names/shapes)"
                        ),
                        severity=9,
                        category="checkpoints",
                    )
                )

        # 3) loss/value compatibility — recorded loss/selection scalars must be finite.
        for checkpoint_key in sorted(checkpoints):
            checkpoint = checkpoints[checkpoint_key]
            if not _is_mapping(checkpoint):
                continue
            for loss_key in _LOSS_KEYS:
                if loss_key not in checkpoint:
                    continue
                if _finite(checkpoint[loss_key]):
                    continue
                findings.append(
                    self.finding(
                        location=Location(cell=cell),
                        issue=(
                            f"Checkpoint '{checkpoint_key}' records non-finite "
                            f"'{loss_key}' = {checkpoint[loss_key]!r}"
                        ),
                        root_cause=(
                            "The checkpoint's recorded loss/selection metric is "
                            "NaN or infinite, indicating a failed or degenerate "
                            "training run"
                        ),
                        impact=(
                            "Model selection based on this checkpoint is "
                            "meaningless; the reported best checkpoint is invalid"
                        ),
                        correction=(
                            "Recompute the loss/metric and re-save a valid "
                            "checkpoint; investigate the training divergence"
                        ),
                        severity=8,
                        category="checkpoints",
                    )
                )

        return findings
