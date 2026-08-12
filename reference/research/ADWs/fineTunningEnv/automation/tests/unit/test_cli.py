"""Tests for nb_audit.cli — the typer app (subcommands + flag → config mapping)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from nb_audit.cli import app

runner = CliRunner()

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


# --------------------------------------------------------------------------- #
# Help surface
# --------------------------------------------------------------------------- #
def test_help_lists_all_four_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in ("audit", "static", "execute", "report"):
        assert sub in result.output


def test_audit_help_lists_all_five_flags():
    result = runner.invoke(app, ["audit", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--config",
        "--max-iterations",
        "--severity-threshold",
        "--no-llm",
        "--allow-network",
    ):
        assert flag in result.output


# --------------------------------------------------------------------------- #
# static — deterministic, LLM-free, exit 0
# --------------------------------------------------------------------------- #
def test_static_runs_llm_free_on_clean_notebook():
    result = runner.invoke(app, ["static", str(FIXTURES / "tiny.ipynb")])
    assert result.exit_code == 0
    assert "finding" in result.output  # "No findings." or "N finding(s)."


def test_static_detects_syntax_error_at_severity_10():
    result = runner.invoke(app, ["static", str(FIXTURES / "syntax_error.ipynb")])
    assert result.exit_code == 0
    assert "severity=10" in result.output


def test_static_missing_notebook_errors_nonzero():
    result = runner.invoke(app, ["static", str(FIXTURES / "does_not_exist.ipynb")])
    assert result.exit_code != 0
    assert "Error" in result.output


# --------------------------------------------------------------------------- #
# report — re-emit from a persisted run
# --------------------------------------------------------------------------- #
def _minimal_audit_json() -> dict:
    return {
        "status": "FAILED",
        "severity_threshold": 8,
        "max_iterations": 2,
        "reason": "max_iterations_exceeded",
        "summary": "Unresolved findings > 8: 1 / Status: FAILED",
        "unresolved_gt8": 1,
        "initial_findings_gt8": [],
        "recurring_findings": [],
        "iteration_history": [
            {
                "iteration": 1,
                "findings": [],
                "unresolved_gt8": [],
                "exec_status": "SUCCESS",
                "qa_status": "PASS",
                "regressions": [],
                "recurring": [],
                "corrections": {},
            }
        ],
        "final_findings": [],
        "checklist": [{"label": "0 unresolved findings > 8", "passed": False}],
    }


def test_report_missing_run_errors_nonzero():
    result = runner.invoke(app, ["report", "nonexistent-run-id"])
    assert result.exit_code != 0
    assert "Error" in result.output


def test_report_existing_run_emits_md_and_json(tmp_path, monkeypatch):
    run_dir = tmp_path / "audit-runs" / "20260101T000000000000"
    run_dir.mkdir(parents=True)
    (run_dir / "audit.json").write_text(
        json.dumps(_minimal_audit_json()), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["report", "20260101T000000000000"])
    assert result.exit_code == 0
    assert (run_dir / "report.md").exists()
    md = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "## FINAL STATUS" in md
    assert "Unresolved findings > 8: 1 / Status: FAILED" in md


def test_report_accepts_full_run_path(tmp_path):
    run_dir = tmp_path / "audit-runs" / "20260101T000000000000"
    run_dir.mkdir(parents=True)
    (run_dir / "audit.json").write_text(
        json.dumps(_minimal_audit_json()), encoding="utf-8"
    )

    result = runner.invoke(app, ["report", str(run_dir)])
    assert result.exit_code == 0
    assert (run_dir / "report.md").exists()


# --------------------------------------------------------------------------- #
# audit — flag → config mapping (loop body is stubbed; no kernel)
# --------------------------------------------------------------------------- #
def test_audit_max_iterations_flag_caps_the_loop(tmp_path, monkeypatch):
    from nb_audit.controller import AuditOutcome
    from nb_audit.io import NotebookManager

    captured: dict = {}

    def fake_run_outcome(notebook, config, no_llm):
        captured["max_iterations"] = config.audit.max_iterations
        captured["no_llm"] = no_llm
        manager = NotebookManager(notebook, base_dir=tmp_path)
        outcome = AuditOutcome(
            status="PASS",
            iterations=[],
            final_findings=[],
            max_iterations=config.audit.max_iterations,
            reason="four_gate_pass",
        )
        return outcome, manager

    monkeypatch.setattr("nb_audit.cli._run_audit_outcome", fake_run_outcome)

    result = runner.invoke(
        app,
        [
            "audit",
            str(FIXTURES / "tiny.ipynb"),
            "--max-iterations",
            "3",
            "--no-llm",
        ],
    )

    assert result.exit_code == 0
    assert captured["max_iterations"] == 3
    assert captured["no_llm"] is True
    assert "Status: PASS" in result.output or "Unresolved findings > 8: 0" in result.output


def test_audit_severity_threshold_flag_maps_to_config(tmp_path, monkeypatch):
    from nb_audit.controller import AuditOutcome
    from nb_audit.io import NotebookManager

    captured: dict = {}

    def fake_run_outcome(notebook, config, no_llm):
        captured["severity_threshold"] = config.audit.severity_threshold
        manager = NotebookManager(notebook, base_dir=tmp_path)
        outcome = AuditOutcome(
            status="PASS",
            iterations=[],
            final_findings=[],
            max_iterations=config.audit.max_iterations,
            reason="four_gate_pass",
        )
        return outcome, manager

    monkeypatch.setattr("nb_audit.cli._run_audit_outcome", fake_run_outcome)

    result = runner.invoke(
        app,
        ["audit", str(FIXTURES / "tiny.ipynb"), "--severity-threshold", "9"],
    )

    assert result.exit_code == 0
    assert captured["severity_threshold"] == 9


def test_audit_failed_outcome_exits_nonzero(tmp_path, monkeypatch):
    from nb_audit.controller import AuditOutcome
    from nb_audit.io import NotebookManager

    def fake_run_outcome(notebook, config, no_llm):
        manager = NotebookManager(notebook, base_dir=tmp_path)
        outcome = AuditOutcome(
            status="FAILED",
            iterations=[],
            final_findings=[],
            max_iterations=config.audit.max_iterations,
            reason="max_iterations_exceeded",
        )
        return outcome, manager

    monkeypatch.setattr("nb_audit.cli._run_audit_outcome", fake_run_outcome)

    result = runner.invoke(
        app, ["audit", str(FIXTURES / "tiny.ipynb"), "--no-llm"]
    )
    assert result.exit_code == 1
