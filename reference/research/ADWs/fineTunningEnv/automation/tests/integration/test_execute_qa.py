"""Integration tests: execute broken fixtures in a real kernel, then run QA.

Each deliberately-broken fixture must reproduce its original failure after
execution + runtime QA. All tests are CPU-only, LLM-free, and use tiny
numpy/Python snippets (no training). They run against the ``python3`` kernel
and SKIP gracefully when that kernel is unavailable.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from nb_audit.config import AuditConfig
from nb_audit.execute import TIMEOUT, NotebookExecutor
from nb_audit.ir import NotebookParser
from nb_audit.qa import FAILED, PASS, RuntimeQA

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


def _config(timeout: int) -> AuditConfig:
    config = AuditConfig()
    config.execution.timeout_seconds = timeout
    return config


def _execute_fixture(name: str, tmp_path: Path, timeout: int = 30):
    notebook_path = FIXTURES / name
    executor = NotebookExecutor(config=_config(timeout), run_dir=tmp_path)
    result = executor.execute_sync(notebook_path)
    model = NotebookParser().parse_file(str(notebook_path))
    return model, result


# -- broken fixtures reproduce their failure --------------------------------- #
@pytest.mark.parametrize(
    ("fixture", "category", "severity", "needle"),
    [
        ("validation_leakage.ipynb", "splits", 9, "TRAIN ∩ VALIDATION"),
        ("train_test_overlap.ipynb", "splits", 9, "TRAIN ∩ TEST"),
        ("checkpoint_not_restored.ipynb", "checkpoints", 9, "never restored"),
        ("metric_mismatch.ipynb", "metrics", 8, "outside the valid range"),
    ],
)
def test_fixture_reproduces_original_failure(tmp_path, fixture, category, severity, needle):
    model, result = _execute_fixture(fixture, tmp_path)

    assert result.status == "SUCCESS", result.error_message
    qa = RuntimeQA(config=_config(30))
    qa_result = qa.run(model, result)

    matches = [f for f in qa_result.findings if f.category == category]
    assert matches, f"no {category} finding produced; got {[f.category for f in qa_result.findings]}"
    assert any(f.severity == severity for f in matches)
    assert any(needle in f.issue for f in matches)


def test_clean_fixture_execution_is_deterministic(tmp_path):
    model1, result1 = _execute_fixture("validation_leakage.ipynb", tmp_path / "a")
    model2, result2 = _execute_fixture("validation_leakage.ipynb", tmp_path / "b")
    qa = RuntimeQA(config=_config(30))
    raw1 = [f.to_raw() for f in qa.run(model1, result1).findings]
    raw2 = [f.to_raw() for f in qa.run(model2, result2).findings]
    assert raw1 == raw2


# -- the hang / timeout RED case (threat matrix) ----------------------------- #
def test_hang_fixture_is_killed_by_per_cell_timeout(tmp_path):
    executor = NotebookExecutor(config=_config(2), run_dir=tmp_path)
    started = time.monotonic()
    result = executor.execute_sync(FIXTURES / "hang.ipynb")
    elapsed = time.monotonic() - started

    assert result.status == TIMEOUT
    assert result.finding is not None
    assert result.finding.severity == 10
    assert result.finding.category == "execution"
    # Bounded wall time: per-cell timeout (2s) + interrupt overhead, never a hang.
    assert elapsed < 30, f"hang test took {elapsed:.1f}s — pipeline hung"


def test_hang_blocks_qa_pass_via_require_clean_execution(tmp_path):
    executor = NotebookExecutor(config=_config(2), run_dir=tmp_path)
    result = executor.execute_sync(FIXTURES / "hang.ipynb")
    model = NotebookParser().parse_file(str(FIXTURES / "hang.ipynb"))

    qa = RuntimeQA(config=_config(2))  # require_clean_execution=True by default
    qa_result = qa.run(model, result)

    assert qa_result.status == FAILED
    assert any(f.category == "execution" and f.severity == 10 for f in qa_result.findings)


# -- allow_network: false is enforced via kernel env ------------------------- #
def test_kernel_env_sets_ip_allow_network_zero(tmp_path):
    import nbformat

    nb = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(
                "import os\n"
                "ip_allow = os.environ.get('IPY_ALLOW_NETWORK')\n"
            )
        ]
    )
    executor = NotebookExecutor(config=_config(30), run_dir=tmp_path)
    result = executor.execute_sync(nb)

    assert result.status == "SUCCESS"
    assert result.namespace.get("ip_allow") == "0"


def test_allow_network_true_leaves_env_unset(tmp_path):
    import nbformat

    nb = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(
                "import os\n"
                "ip_allow = os.environ.get('IPY_ALLOW_NETWORK')\n"
            )
        ]
    )
    executor = NotebookExecutor(config=_config(30), run_dir=tmp_path)
    result = executor.execute_sync(nb, allow_network=True)

    assert result.status == "SUCCESS"
    assert result.namespace.get("ip_allow") is None


# -- execution failure (runtime error) surfaces a sev-10 finding ------------- #
def test_runtime_error_cell_yields_sev10_execution_finding(tmp_path):
    import nbformat

    nb = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_code_cell("1 / 0\n")]
    )
    executor = NotebookExecutor(config=_config(30), run_dir=tmp_path)
    result = executor.execute_sync(nb)

    assert result.status == "ERROR"
    assert result.finding is not None
    assert result.finding.severity == 10
    assert result.finding.category == "execution"
