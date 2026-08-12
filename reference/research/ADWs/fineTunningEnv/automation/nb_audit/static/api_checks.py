"""Heuristic checks for known torch / sklearn / torchvision API misuse.

Deterministic and LLM-free. Each check is a conservative AST/call-name heuristic,
so it may miss some misuses but never depends on execution or an LLM:

- **missing zero_grad** — an optimizer step (``*.step()``) with no
  ``*.zero_grad()`` call anywhere in the notebook.
- **train/eval mode** — evaluation metrics computed after ``model.train()``
  without a matching ``model.eval()`` (dropout/batchnorm stay active).
- **softmax + CrossEntropyLoss** — a ``softmax``/``log_softmax`` call and a
  ``CrossEntropyLoss``/``cross_entropy``/``nll_loss`` call both present, which
  usually means logits are double-softmaxed.
"""

from __future__ import annotations

import ast

from nb_audit.ir import NotebookModel
from nb_audit.models import Finding, Location
from nb_audit.static.check_registry import StaticCheck

_SOFTMAX = frozenset({"softmax", "log_softmax"})
_CROSS_ENTROPY = frozenset({"CrossEntropyLoss", "cross_entropy", "nll_loss"})

# Optimizer constructor names (subset mirroring ir._OPTIMIZER_NAMES) used to gate
# the zero_grad check so scheduler-only ``.step()`` calls are not false-flagged.
_OPTIMIZER_NAMES = frozenset({
    "Adam", "AdamW", "SGD", "RMSprop", "Adagrad", "Adadelta", "Adamax",
    "NAdam", "RAdam", "LBFGS", "ASGD", "SparseAdam", "Rprop",
})

_METRIC_NAMES = frozenset({
    "accuracy_score", "f1_score", "precision_score", "recall_score",
    "roc_auc_score", "confusion_matrix", "classification_report",
    "mean_squared_error", "mean_absolute_error", "r2_score", "log_loss",
})


def _dotted_name(node: ast.Call) -> str:
    parts: list[str] = []
    func: ast.expr = node.func
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    else:
        return ""
    return ".".join(reversed(parts))


class _CallScan:
    def __init__(self, model: NotebookModel) -> None:
        self.calls: list[tuple[str, int, int, str]] = []  # (cell_id, index, line, dotted)
        for cell in model.code_cells:
            if cell.ast is None:
                continue
            for node in ast.walk(cell.ast):
                if not isinstance(node, ast.Call):
                    continue
                dotted = _dotted_name(node)
                if dotted:
                    line = getattr(node, "lineno", None) or 0
                    self.calls.append((cell.id, cell.index, line, dotted))


class ApiChecksCheck(StaticCheck):
    """Known torch/sklearn/torchvision misuse heuristics."""

    name = "api_checks"
    category = "api_misuse"
    severity = 8

    def check(self, model: NotebookModel) -> list[Finding]:
        scan = _CallScan(model)
        findings: list[Finding] = []
        findings.extend(self._zero_grad(model, scan))
        findings.extend(self._train_eval_mode(scan))
        findings.extend(self._softmax_cross_entropy(scan))
        return findings

    # -- zero_grad --------------------------------------------------------- #
    def _zero_grad(self, model: NotebookModel, scan: _CallScan) -> list[Finding]:
        has_optimizer = bool(model.optimizers) or any(
            dotted.split(".")[-1] in _OPTIMIZER_NAMES for *_, dotted in scan.calls
        )
        step_calls = [c for c in scan.calls if c[3].endswith(".step")]
        zero_grad_calls = [c for c in scan.calls if c[3].endswith(".zero_grad")]
        if not (has_optimizer and step_calls and not zero_grad_calls):
            return []
        cell, _index, line, dotted = step_calls[0]
        return [
            self.finding(
                location=Location(cell=cell, line=line),
                issue=f"optimizer step ('{dotted}') with no zero_grad() call",
                root_cause=(
                    "An optimizer .step() is present but no .zero_grad() call exists, "
                    "so gradients accumulate across iterations"
                ),
                impact="Gradients from previous steps leak into the current update",
                correction="Call optimizer.zero_grad() before each backward()/step()",
                severity=8,
                category="api_misuse",
            )
        ]

    # -- train/eval mode --------------------------------------------------- #
    def _train_eval_mode(self, scan: _CallScan) -> list[Finding]:
        train_calls = [c for c in scan.calls if c[3].endswith(".train")]
        eval_calls = [c for c in scan.calls if c[3].endswith(".eval")]
        metric_calls = [
            c for c in scan.calls if c[3].split(".")[-1] in _METRIC_NAMES
        ]
        if not (train_calls and metric_calls and not eval_calls):
            return []
        cell, _index, line, _dotted = metric_calls[0]
        return [
            self.finding(
                location=Location(cell=cell, line=line),
                issue="evaluation metric computed after model.train() without model.eval()",
                root_cause=(
                    "The model is in training mode (model.train()) when metrics are "
                    "computed, so dropout/batchnorm remain active"
                ),
                impact="Evaluation metrics are noisy and not representative of inference",
                correction="Call model.eval() (and torch.no_grad()) before evaluation",
                severity=7,
                category="api_misuse",
            )
        ]

    # -- softmax + CrossEntropyLoss ---------------------------------------- #
    def _softmax_cross_entropy(self, scan: _CallScan) -> list[Finding]:
        softmax_calls = [c for c in scan.calls if c[3].split(".")[-1] in _SOFTMAX]
        loss_calls = [
            c for c in scan.calls if c[3].split(".")[-1] in _CROSS_ENTROPY
        ]
        if not (softmax_calls and loss_calls):
            return []
        cell, _index, line, dotted = softmax_calls[0]
        return [
            self.finding(
                location=Location(cell=cell, line=line),
                issue=f"'{dotted}' used together with CrossEntropyLoss/cross_entropy",
                root_cause=(
                    "CrossEntropyLoss already applies log-softmax internally; an extra "
                    "softmax/log_softmax on the logits is a common double-softmax mistake"
                ),
                impact="Gradients and loss are computed on the wrong scale",
                correction="Remove the explicit softmax when feeding logits to CrossEntropyLoss",
                severity=8,
                category="api_misuse",
            )
        ]
