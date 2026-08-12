"""Regression tests: fixed severity>8 fixtures no longer reproduce their failure.

For every fixed high-severity issue (§28), the pipeline preserves both the broken
fixture and its corrected counterpart. This module proves the core pipeline
invariant — a finding is resolved only when the corrected notebook no longer
contains the underlying problem (§1): the severity>8 signatures produced by the
broken fixture must be ABSENT from the fixed fixture's findings.

CPU-only, LLM-free, kernel-gated (skips when the ``python3`` kernel is absent).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nb_audit.config import AuditConfig
from nb_audit.execute import NotebookExecutor
from nb_audit.ir import NotebookParser
from nb_audit.qa import RuntimeQA

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# Each broken fixture's corrected counterpart (a fixed severity>8 issue).
PAIRS = [
    ("validation_leakage.ipynb", "validation_leakage_fixed.ipynb"),
    ("train_test_overlap.ipynb", "train_test_overlap_fixed.ipynb"),
    ("checkpoint_not_restored.ipynb", "checkpoint_not_restored_fixed.ipynb"),
]


def _kernel_available(name: str = "python3") -> bool:
    try:
        from jupyter_client.kernelspec import KernelSpecManager

        return name in KernelSpecManager().find_kernel_specs()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _kernel_available(),
    reason="python3 kernel not available — skipping kernel-dependent regression tests",
)


def _config(timeout: int = 30) -> AuditConfig:
    config = AuditConfig()
    config.execution.timeout_seconds = timeout
    return config


def _run_fixture(fixture: str, tmp_path: Path):
    """Execute + runtime-QA one fixture, returning (exec_result, findings)."""
    executor = NotebookExecutor(config=_config(), run_dir=tmp_path)
    result = executor.execute_sync(FIXTURES / fixture)
    model = NotebookParser().parse_file(str(FIXTURES / fixture))
    findings = RuntimeQA(config=_config()).run(model, result).findings
    return result, findings


@pytest.mark.parametrize(("broken", "fixed"), PAIRS)
def test_fixed_fixture_resolves_original_severity_gt8_signature(
    tmp_path, broken, fixed
):
    # The broken fixture must reproduce its severity>8 failure (sanity gate).
    _, broken_findings = _run_fixture(broken, tmp_path / "broken")
    broken_sigs = {f.signature for f in broken_findings if f.severity > 8}
    assert broken_sigs, f"{broken} produced no severity>8 findings"

    # The fixed fixture executes cleanly and drops the original signatures.
    fixed_result, fixed_findings = _run_fixture(fixed, tmp_path / "fixed")
    assert fixed_result.status == "SUCCESS", fixed_result.error_message
    fixed_sigs = {f.signature for f in fixed_findings if f.severity > 8}

    # Original severity>8 signatures are ABSENT in the fixed notebook (resolved).
    assert not (broken_sigs & fixed_sigs), (
        f"fixed {fixed} still reproduces signatures: {broken_sigs & fixed_sigs}"
    )
    # Stronger: the fixed notebook has no severity>8 findings at all.
    assert not fixed_sigs, [
        f.to_raw() for f in fixed_findings if f.severity > 8
    ]
