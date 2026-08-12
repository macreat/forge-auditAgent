"""Runtime tensor/model-interface checks (§6.2).

Asserts the deterministic tensor invariants that only become observable after
execution, working purely through duck-typing (``shape`` / ``dtype`` / ``device``
attributes) so it works with PyTorch tensors, NumPy arrays, and lightweight test
doubles alike:

- **batch dimension** — ``logits.shape[0] == labels.shape[0]`` (severity 9);
- **device placement** — prediction and label tensors must live on the same
  device (severity 9);
- **dtype compatibility** — integer predictions vs. floating labels (or boolean
  labels) is almost always a bug (severity 8).
"""

from __future__ import annotations

from typing import Mapping

from nb_audit.ir import NotebookModel
from nb_audit.models import Finding, Location
from nb_audit.mlqa.check_registry import RuntimeCheck

_PRED_NAMES = (
    "logits", "preds", "predictions", "pred", "y_pred", "y_hat",
    "outputs", "output", "probs", "probabilities", "scores",
)
_LABEL_NAMES = (
    "labels", "targets", "target", "y_true", "y", "ground_truth", "gold",
)

_FLOAT_KINDS = ("float", "half", "double", "bfloat")
_INT_KINDS = ("int", "long", "short", "uint", "byte", "char")


def _is_tensor_like(obj) -> bool:
    return hasattr(obj, "shape")


def _pick(ctx: Mapping, names) -> tuple[str, object] | tuple[None, None]:
    """Return the first present, tensor-like entry matching one of ``names``."""
    for name in names:
        for key, value in ctx.items():
            if str(key).lower() == name and _is_tensor_like(value):
                return str(key), value
    return None, None


def _dim0(obj) -> int | None:
    shape = getattr(obj, "shape", None)
    if shape is None:
        return None
    try:
        if len(shape) == 0:
            return None  # scalar tensor
        return int(shape[0])
    except (TypeError, IndexError):
        return None


def _device(obj) -> str:
    device = getattr(obj, "device", None)
    if device is None:
        return ""
    return str(device)


def _dtype_kind(obj) -> str:
    dtype = getattr(obj, "dtype", None)
    if dtype is None:
        return ""
    text = str(dtype).lower()
    if any(k in text for k in ("bool",)):
        return "bool"
    if any(k in text for k in _FLOAT_KINDS):
        return "float"
    if any(k in text for k in _INT_KINDS):
        return "int"
    return "other"


class TensorCheck(RuntimeCheck):
    """Shape, device, and dtype invariants between prediction and label tensors."""

    name = "tensors"
    category = "tensors"
    severity = 9

    def check(self, model: NotebookModel, ctx: Mapping) -> list[Finding]:
        pred_key, pred = _pick(ctx, _PRED_NAMES)
        label_key, label = _pick(ctx, _LABEL_NAMES)
        if pred is None or label is None:
            return []

        findings: list[Finding] = []

        # 1) batch dimension mismatch.
        pred_n = _dim0(pred)
        label_n = _dim0(label)
        if pred_n is not None and label_n is not None and pred_n != label_n:
            findings.append(
                self.finding(
                    location=Location(),
                    issue=(
                        f"Batch size mismatch: {pred_key}.shape[0]={pred_n} != "
                        f"{label_key}.shape[0]={label_n}"
                    ),
                    root_cause=(
                        "The number of predictions does not match the number of "
                        "labels (logits.shape[0] != labels.shape[0])"
                    ),
                    impact=(
                        "Loss/metrics are computed on misaligned tensors, so the "
                        "reported results are wrong"
                    ),
                    correction="Align predictions and labels along the batch dimension",
                    severity=9,
                    category="tensors",
                )
            )

        # 2) device placement mismatch.
        pred_dev = _device(pred)
        label_dev = _device(label)
        if pred_dev and label_dev and pred_dev != label_dev:
            findings.append(
                self.finding(
                    location=Location(),
                    issue=(
                        f"Device mismatch: {pred_key} is on '{pred_dev}' but "
                        f"{label_key} is on '{label_dev}'"
                    ),
                    root_cause=(
                        "Predictions and labels are placed on different devices "
                        "(e.g. CPU vs CUDA)"
                    ),
                    impact="Operations between them raise at runtime or silently fail",
                    correction="Move both tensors to the same device before the comparison",
                    severity=9,
                    category="tensors",
                )
            )

        # 3) dtype incompatibility.
        pred_kind = _dtype_kind(pred)
        label_kind = _dtype_kind(label)
        if pred_kind == "int" and label_kind == "float":
            findings.append(
                self.finding(
                    location=Location(),
                    issue=(
                        f"dtype incompatibility: {pred_key} is integer while "
                        f"{label_key} is floating-point"
                    ),
                    root_cause=(
                        "Integer predictions are paired with floating-point labels, "
                        "which is not a valid regression/classification pairing"
                    ),
                    impact="Loss computation is ill-defined; the experiment is invalid",
                    correction="Fix the prediction or label dtype so they are compatible",
                    severity=8,
                    category="tensors",
                )
            )
        elif label_kind == "bool":
            findings.append(
                self.finding(
                    location=Location(),
                    issue=f"Boolean labels detected in '{label_key}'",
                    root_cause="Labels are boolean, which is incompatible with typical losses",
                    impact="Loss/metrics behave unexpectedly with boolean targets",
                    correction="Convert labels to the appropriate numeric dtype",
                    severity=8,
                    category="tensors",
                )
            )

        return findings
