"""Deterministic MockBackend for the semantic auditor (offline tests, no LLM).

Returns a fixed, schema-valid finding payload regardless of the prompt, so
tests and offline runs exercise the same render → validate path as the real
backend without any network or live model. The findings are guaranteed to pass
:meth:`Backend.validate_findings` (schema validity) and are byte-identical
across calls (determinism).
"""

from __future__ import annotations

import json

from nb_audit.semantic.backend import Backend

# Deterministic, schema-valid finding payload. Two findings across two
# categories to exercise multi-finding parsing; every field the validator
# checks is populated. Severity values are chosen above the patch threshold
# (> 8) so the mock is also useful for end-to-end repair tests in later slices.
MOCK_FINDINGS: tuple[dict, ...] = (
    {
        "severity": 9,
        "category": "metrics",
        "issue": "Accuracy is reported for the test split but the best checkpoint was selected on validation loss",
        "location": {"cell": "cell-eval", "line": 3},
        "root_cause": "Metric used for model selection differs from the metric reported",
        "impact": "The reported test accuracy does not reflect the selection protocol",
        "correction": "Report the selection metric alongside the test metric",
        "classification": "NEW",
    },
    {
        "severity": 8,
        "category": "conclusions",
        "issue": "Conclusion claims state-of-the-art performance but no baseline comparison is present",
        "location": {"cell": "cell-markdown", "line": None},
        "root_cause": "Conclusion asserts more than the experiment demonstrates",
        "impact": "Unsupported claim may mislead readers about the experiment",
        "correction": "Narrow the conclusion to the demonstrated comparison or add the baseline",
        "classification": "NEW",
    },
)


class MockBackend(Backend):
    """Semantic auditor backend returning deterministic, schema-valid findings."""

    def __init__(
        self,
        max_retries: int = 2,
        backoff_seconds: float = 0.0,
        findings: tuple[dict, ...] | list[dict] | None = None,
    ) -> None:
        super().__init__(max_retries=max_retries, backoff_seconds=backoff_seconds)
        self._findings = list(findings) if findings is not None else list(MOCK_FINDINGS)

    async def _generate(self, prompt: str) -> str:
        """Return the fixed finding payload as strict JSON (no network, no LLM)."""
        return json.dumps({"findings": self._findings})

    def payload(self) -> str:
        """Return the deterministic raw JSON payload (for round-trip harnesses)."""
        return json.dumps({"findings": self._findings})
