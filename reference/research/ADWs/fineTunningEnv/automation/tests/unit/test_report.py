"""Tests for nb_audit.report — audit.json + report.md generation (§25, §22)."""

from __future__ import annotations

import json

import pytest

from nb_audit.controller import FAILED, PASS, AuditOutcome, IterationRecord
from nb_audit.models import Classification, Finding, Location, Status
from nb_audit.report import (
    blocking_findings,
    build_audit_json,
    build_checklist,
    build_report_documents,
    initial_findings_gt8,
    load_audit_json,
    recurring_findings,
    render_markdown,
    summary_line,
    write_report,
    write_report_documents,
)


def _finding(
    *,
    severity: int = 9,
    category: str = "splits",
    cell: str = "c1",
    status: Status = Status.UNRESOLVED,
    fid: str = "F0001",
    regression: bool = False,
    root_cause: str = "partitions are not disjoint",
) -> Finding:
    return Finding(
        id=fid,
        severity=severity,
        classification=Classification.NEW,
        category=category,
        location=Location(cell=cell, line=1),
        issue="data leakage",
        root_cause=root_cause,
        status=status,
        regression=regression,
    )


def _iter(
    iteration: int,
    findings: list[Finding],
    *,
    exec_status: str = "SUCCESS",
    qa_status: str = "PASS",
    recurring: list[Finding] | None = None,
    regressions: list[Finding] | None = None,
    corrections: dict | None = None,
) -> IterationRecord:
    return IterationRecord(
        iteration=iteration,
        findings=findings,
        unresolved_gt8=[f for f in findings if f.severity > 8],
        exec_status=exec_status,
        qa_status=qa_status,
        recurring=recurring or [],
        regressions=regressions or [],
        corrections=corrections or {},
    )


def _pass_outcome() -> AuditOutcome:
    return AuditOutcome(
        status=PASS,
        iterations=[_iter(1, [])],
        final_findings=[],
        max_iterations=1,
        reason="four_gate_pass",
    )


def _failed_outcome() -> AuditOutcome:
    leak = _finding(fid="F0001")
    again = _finding(fid="F0002")  # same signature, freshly re-registered
    return AuditOutcome(
        status=FAILED,
        iterations=[
            _iter(1, [leak]),
            _iter(2, [again], recurring=[again]),
        ],
        final_findings=[again],
        max_iterations=2,
        reason="max_iterations_exceeded",
    )


# --------------------------------------------------------------------------- #
# Finding selection helpers
# --------------------------------------------------------------------------- #
def test_blocking_findings_excludes_resolved_and_wont_fix():
    resolved = _finding(status=Status.RESOLVED, fid="F0002")
    wont_fix = _finding(status=Status.WONT_FIX, fid="F0003")
    unresolved = _finding(fid="F0001")
    at_threshold = _finding(severity=8, fid="F0004")

    blocking = blocking_findings([resolved, wont_fix, unresolved, at_threshold])
    assert [f.id for f in blocking] == ["F0001"]


def test_initial_findings_gt8_only_from_first_iteration():
    outcome = _failed_outcome()
    initial = initial_findings_gt8(outcome)
    assert [f.id for f in initial] == ["F0001"]


def test_initial_findings_gt8_empty_when_no_iterations():
    outcome = AuditOutcome(
        status=FAILED, iterations=[], final_findings=[], max_iterations=1, reason="x"
    )
    assert initial_findings_gt8(outcome) == []


def test_recurring_findings_deduplicated_by_signature():
    outcome = _failed_outcome()
    recurring = recurring_findings(outcome)
    # F0001 (from iteration 1's transition) and F0002 (iteration 2's marker)
    # share one signature; the report keeps a single entry.
    assert len(recurring) == 1
    assert recurring[0].id == "F0002"


def test_recurring_findings_includes_transitioned_status():
    leak = _finding(fid="F0001", status=Status.RECURRING)
    outcome = AuditOutcome(
        status=FAILED,
        iterations=[_iter(1, [leak])],
        final_findings=[leak],
        max_iterations=1,
        reason="x",
    )
    assert [f.id for f in recurring_findings(outcome)] == ["F0001"]


# --------------------------------------------------------------------------- #
# Summary line
# --------------------------------------------------------------------------- #
def test_summary_line_format():
    assert summary_line(0, PASS) == "Unresolved findings > 8: 0 / Status: PASS"
    assert summary_line(3, FAILED) == "Unresolved findings > 8: 3 / Status: FAILED"


# --------------------------------------------------------------------------- #
# Checklist
# --------------------------------------------------------------------------- #
def test_checklist_has_ten_items():
    items = build_checklist(_pass_outcome())
    assert len(items) == 10
    assert all(item["passed"] for item in items)


def test_checklist_fails_mechanical_and_semantic_items_when_unresolved():
    items = build_checklist(_failed_outcome())
    by_label = {item["label"]: item["passed"] for item in items}

    assert by_label["0 unresolved findings > 8"] is False
    assert by_label["no previous >8 issue remains unresolved"] is False
    assert by_label["no new >8 regression"] is True  # no patch-induced regression
    # splits maps to the protocol-consistency item.
    assert by_label["experimental protocol agrees with implementation"] is False
    # unrelated semantic items still hold.
    assert by_label["metrics match definitions"] is True


# --------------------------------------------------------------------------- #
# audit.json document
# --------------------------------------------------------------------------- #
def test_audit_json_parses_and_has_required_sections():
    doc = build_audit_json(_failed_outcome())
    # parses as JSON (round-trips through the serializer).
    reloaded = json.loads(json.dumps(doc))
    assert reloaded["status"] == FAILED
    assert reloaded["unresolved_gt8"] == 1
    assert reloaded["summary"] == "Unresolved findings > 8: 1 / Status: FAILED"
    assert reloaded["initial_findings_gt8"][0]["id"] == "F0001"
    assert len(reloaded["iteration_history"]) == 2
    assert len(reloaded["recurring_findings"]) == 1
    assert len(reloaded["checklist"]) == 10


def test_audit_json_pass_has_zero_unresolved():
    doc = build_audit_json(_pass_outcome())
    assert doc["status"] == PASS
    assert doc["unresolved_gt8"] == 0
    assert doc["summary"] == "Unresolved findings > 8: 0 / Status: PASS"


# --------------------------------------------------------------------------- #
# report.md rendering
# --------------------------------------------------------------------------- #
def test_report_md_contains_required_sections():
    md = render_markdown(build_audit_json(_failed_outcome()))
    assert "# Final Audit" in md
    assert "## FINAL STATUS" in md
    assert "Unresolved findings > 8: 1 / Status: FAILED" in md
    assert "## Final Verification" in md
    assert "## Iteration History" in md
    assert "## Recurring Issues" in md
    assert "## Initial Findings > 8" in md
    assert "- [x] 0 unresolved findings > 8" not in md  # it failed
    assert "- [ ] 0 unresolved findings > 8" in md


def test_report_md_renders_checklist_and_iterations():
    md = render_markdown(build_audit_json(_pass_outcome()))
    assert "- [x] 0 unresolved findings > 8" in md
    assert "### Iteration 1" in md


# --------------------------------------------------------------------------- #
# Filesystem writes
# --------------------------------------------------------------------------- #
def test_write_report_documents_writes_parseable_json_and_md(tmp_path):
    docs = build_report_documents(_failed_outcome())
    json_path, md_path = write_report_documents(docs, tmp_path / "run")

    assert json_path.exists() and md_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["status"] == FAILED
    assert "## FINAL STATUS" in md_path.read_text(encoding="utf-8")


def test_write_report_convenience(tmp_path):
    json_path, md_path = write_report(_pass_outcome(), tmp_path / "run")
    assert json_path.name == "audit.json"
    assert md_path.name == "report.md"


def test_load_audit_json_round_trips(tmp_path):
    docs = build_report_documents(_failed_outcome())
    write_report_documents(docs, tmp_path / "run")
    loaded = load_audit_json(tmp_path / "run")
    assert loaded["summary"] == docs.audit_json["summary"]


def test_load_audit_json_missing_run_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_audit_json(tmp_path / "missing-run")
