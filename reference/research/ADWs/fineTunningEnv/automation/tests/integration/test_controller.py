"""Integration tests for the iteration controller (spec §21, §22).

Runs the controller over real fixtures in a real ``python3`` kernel with the
static-only auditor (NO LLM) and the no-op patcher, proving:

- an unresolved severity-9 leakage finding drives the loop to ``FAILED`` at the
  iteration cap (and is flagged recurring), and
- a clean notebook satisfies all four gates and returns ``PASS``.

Tests SKIP gracefully when the ``python3`` kernel is unavailable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nb_audit.config import AuditConfig
from nb_audit.controller import FAILED, PASS, AuditController
from nb_audit.ir import NotebookModel, NotebookParser

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _kernel_available(name: str = "python3") -> bool:
    try:
        from jupyter_client.kernelspec import KernelSpecManager
        return name in KernelSpecManager().find_kernel_specs()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _kernel_available(),
    reason="python3 kernel not available — skipping kernel-dependent integration tests",
)


def _config(timeout: int = 30, max_iterations: int = 3) -> AuditConfig:
    config = AuditConfig()
    config.execution.timeout_seconds = timeout
    config.audit.max_iterations = max_iterations
    return config


def _clean_model() -> NotebookModel:
    import nbformat

    nb = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_code_cell("answer = 42\n")]
    )
    return NotebookParser().parse(json.dumps(nb))


def test_controller_fails_on_unresolved_leakage(tmp_path):
    model = NotebookParser().parse_file(str(FIXTURES / "validation_leakage.ipynb"))
    controller = AuditController(
        config=_config(max_iterations=2),
        run_dir=tmp_path,
    )
    outcome = controller.run(model)

    assert outcome.status == FAILED
    assert not outcome.passed
    assert outcome.max_iterations == 2
    assert len(outcome.iterations) == 2
    assert outcome.reason == "max_iterations_exceeded"

    # the leakage finding is a severity-9 splits finding and blocks PASS
    leakage = [f for f in outcome.final_findings if f.category == "splits"]
    assert leakage, [f.category for f in outcome.final_findings]
    assert any(f.severity == 9 and "TRAIN ∩ VALIDATION" in f.issue for f in leakage)

    # the persisting leakage signature is flagged recurring on the 2nd iteration
    assert any(
        f.category == "splits" for f in outcome.iterations[1].recurring
    )


def test_controller_passes_on_clean_notebook(tmp_path):
    model = _clean_model()
    controller = AuditController(
        config=_config(max_iterations=3),
        run_dir=tmp_path,
    )
    outcome = controller.run(model)

    assert outcome.status == PASS
    assert outcome.passed
    assert len(outcome.iterations) == 1
    assert outcome.iterations[0].exec_status == "SUCCESS"
    assert outcome.iterations[0].qa_status == "PASS"


def test_max_iterations_caps_the_loop(tmp_path):
    model = NotebookParser().parse_file(str(FIXTURES / "validation_leakage.ipynb"))
    controller = AuditController(
        config=_config(max_iterations=2),
        run_dir=tmp_path,
    )
    outcome = controller.run(model)

    # the loop must never exceed the configured cap, even though the leakage
    # finding never resolves (no-op patcher, static-only audit).
    assert len(outcome.iterations) == 2
    assert outcome.status == FAILED
