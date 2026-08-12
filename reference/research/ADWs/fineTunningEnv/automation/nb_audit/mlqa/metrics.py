"""Runtime metric checks: range, zero-division, and averaging sanity (§6.9).

Inspects metric scalars present in the executed namespace (``accuracy``,
``precision``, ``recall``, ``f1``, ``auc``, ...) and asserts:

- **range** — proportion metrics must lie in ``[0, 1]`` (severity 8);
- **zero-division** — ``NaN`` / infinite metric values indicate an unhandled
  zero division (severity 8);
- **averaging sanity** — a per-class array (``average=None``) surfaced as a single
  scalar metric is ambiguous (severity 7).
"""

from __future__ import annotations

import math
from typing import Mapping

from nb_audit.ir import NotebookModel
from nb_audit.models import Finding, Location
from nb_audit.mlqa.check_registry import RuntimeCheck

# Proportion metrics constrained to [0, 1].
_PROPORTION_METRICS = (
    "accuracy", "acc", "balanced_accuracy", "precision", "recall",
    "f1", "f1_score", "fbeta", "fscore", "auc", "roc_auc",
    "average_precision", "ap", "sensitivity", "specificity",
)

_EPS = 1e-6


def _is_metric_name(name: str) -> bool:
    low = name.lower()
    return low in _PROPORTION_METRICS or any(
        low.endswith(suffix)
        for suffix in ("_accuracy", "_precision", "_recall", "_f1", "_auc", "_score")
    )


def _metric_value(obj):
    """Return ``(value, is_multi)`` for a scalar, 0-d array, or 1-element list."""
    # 0-d numpy scalar / torch scalar tensor.
    if hasattr(obj, "item") and callable(obj.item) and hasattr(obj, "ndim"):
        try:
            if obj.ndim == 0:
                return obj.item(), False
        except Exception:  # pragma: no cover - defensive
            pass
    if hasattr(obj, "item") and callable(obj.item) and hasattr(obj, "shape"):
        try:
            if len(obj.shape) == 0:
                return obj.item(), False
        except Exception:  # pragma: no cover - defensive
            pass
    if isinstance(obj, (list, tuple)):
        if len(obj) == 1:
            return obj[0], False
        return obj, len(obj) > 1
    return obj, False


class MetricCheck(RuntimeCheck):
    """Metric range, zero-division, and averaging checks."""

    name = "metrics"
    category = "metrics"
    severity = 8

    def check(self, model: NotebookModel, ctx: Mapping) -> list[Finding]:
        findings: list[Finding] = []

        for key, raw in ctx.items():
            name = str(key)
            if not _is_metric_name(name):
                continue
            value, is_multi = _metric_value(raw)

            # averaging sanity: per-class array surfaced as a scalar metric.
            if is_multi:
                findings.append(
                    self.finding(
                        location=Location(),
                        issue=(
                            f"Metric '{name}' holds {len(value)} values (per-class "
                            "array) — averaging method is unclear"
                        ),
                        root_cause=(
                            "A metric computed with average=None (or a per-class "
                            "result) is stored as a multi-value array"
                        ),
                        impact=(
                            "A scalar was expected; the reported number may be a "
                            "mis-selected class or an unsupported aggregate"
                        ),
                        correction="Choose an explicit averaging method (e.g. macro/weighted)",
                        severity=7,
                        category="metrics",
                    )
                )
                continue

            # non-numeric values are out of scope.
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue

            # zero-division / non-finite.
            if math.isnan(numeric):
                findings.append(
                    self.finding(
                        location=Location(),
                        issue=f"Metric '{name}' is NaN (likely zero-division)",
                        root_cause="A metric produced NaN, typically from a 0/0 division",
                        impact="The reported metric is meaningless",
                        correction="Handle zero-division (zero_division=...) or fix the metric inputs",
                        severity=8,
                        category="metrics",
                    )
                )
                continue
            if math.isinf(numeric):
                findings.append(
                    self.finding(
                        location=Location(),
                        issue=f"Metric '{name}' is infinite",
                        root_cause="A metric produced ±inf, typically from division by zero",
                        impact="The reported metric is meaningless",
                        correction="Handle zero-division or fix the metric inputs",
                        severity=8,
                        category="metrics",
                    )
                )
                continue

            # range for proportion metrics.
            if name.lower() in _PROPORTION_METRICS:
                if numeric < -_EPS or numeric > 1 + _EPS:
                    findings.append(
                        self.finding(
                            location=Location(),
                            issue=(
                                f"Metric '{name}' = {numeric} is outside the valid "
                                "range [0, 1]"
                            ),
                            root_cause=(
                                "A proportion metric (accuracy/precision/recall/f1/"
                                "auc) fell outside [0, 1]"
                            ),
                            impact=(
                                "The metric computation is incorrect or uses the "
                                "wrong inputs/scale"
                            ),
                            correction="Recompute the metric; verify inputs and normalization",
                            severity=8,
                            category="metrics",
                        )
                    )

        return findings
