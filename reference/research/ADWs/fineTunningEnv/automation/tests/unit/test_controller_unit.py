"""Tests for nb_audit.controller — the §21 loop + four-gate PASS predicate.

All tests are kernel-independent and LLM-free: they inject fake auditors,
executors, QA and patchers to drive the loop deterministically (REQ-016).
"""

from __future__ import annotations

from nb_audit.config import AuditConfig
from nb_audit.controller import (
    FAILED,
    PASS,
    AuditController,
    IterationRecord,
    PatchOutcome,
    four_gate_pass,
)
from nb_audit.execute import SUCCESS, ExecutionResult
from nb_audit.ir import NotebookModel
from nb_audit.models import Classification, Finding, Location, Status, compute_signature
from nb_audit.qa import FAILED as QA_FAILED
from nb_audit.qa import PASS as QA_PASS
from nb_audit.qa import QAResult


def _finding(
    *,
    severity: int = 9,
    category: str = "leakage",
    cell: str = "c1",
    root_cause: str = "partitions are not disjoint",
) -> Finding:
    return Finding(
        id="",
        severity=severity,
        classification=Classification.NEW,
        category=category,
        location=Location(cell=cell, line=1),
        issue="data leakage",
        root_cause=root_cause,
    )


# The deterministic signature of the default _finding() fixture.
LEAK_SIG = compute_signature(
    "partitions are not disjoint", "leakage", Location(cell="c1", line=1)
)


def _model() -> NotebookModel:
    return NotebookModel()


def _ok_exec() -> ExecutionResult:
    return ExecutionResult(status=SUCCESS)


def _fail_exec() -> ExecutionResult:
    return ExecutionResult(
        status="ERROR",
        finding=_finding(severity=10, category="execution", root_cause="runtime error"),
    )


def _ok_qa() -> QAResult:
    return QAResult(status=QA_PASS)


def _fail_qa() -> QAResult:
    return QAResult(
        status=QA_FAILED,
        findings=[_finding(severity=10, category="execution", root_cause="runtime error")],
    )


# --------------------------------------------------------------------------- #
# four_gate_pass — a failure of ANY gate → not PASS
# --------------------------------------------------------------------------- #
def test_four_gate_pass_requires_all_four():
    no_findings: list[Finding] = []
    one_finding = [_finding()]
    no_regressions: list[Finding] = []
    one_regression = [_finding()]

    # all gates hold
    assert four_gate_pass(no_findings, SUCCESS, QA_PASS, no_regressions)

    # findings gate fails
    assert not four_gate_pass(one_finding, SUCCESS, QA_PASS, no_regressions)
    # execution gate fails
    assert not four_gate_pass(no_findings, "ERROR", QA_PASS, no_regressions)
    # qa gate fails
    assert not four_gate_pass(no_findings, SUCCESS, QA_FAILED, no_regressions)
    # regression gate fails
    assert not four_gate_pass(no_findings, SUCCESS, QA_PASS, one_regression)
    # everything fails
    assert not four_gate_pass(one_finding, "ERROR", QA_FAILED, one_regression)


# --------------------------------------------------------------------------- #
# PASS — all four gates hold on the first iteration
# --------------------------------------------------------------------------- #
def test_pass_when_all_four_gates_hold():
    controller = AuditController(
        auditor=lambda model: [],
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        max_iterations=3,
    )
    outcome = controller.run(_model())

    assert outcome.status == PASS
    assert outcome.passed
    assert len(outcome.iterations) == 1
    assert outcome.reason == "four_gate_pass"


def test_severity_at_threshold_does_not_block():
    # a severity-8 finding is NOT > threshold, so it does not block PASS.
    controller = AuditController(
        auditor=lambda model: [_finding(severity=8)],
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        max_iterations=3,
    )
    outcome = controller.run(_model())
    assert outcome.status == PASS


# --------------------------------------------------------------------------- #
# FAILED at max iterations with unresolved severity>8
# --------------------------------------------------------------------------- #
def test_failed_at_max_iterations_with_unresolved_gt8():
    controller = AuditController(
        auditor=lambda model: [_finding()],  # persists forever
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        patcher=lambda unresolved, model, prior: PatchOutcome(model=model),  # no-op
        max_iterations=5,
    )
    outcome = controller.run(_model())

    assert outcome.status == FAILED
    assert not outcome.passed
    assert len(outcome.iterations) == 5
    assert outcome.reason == "max_iterations_exceeded"
    assert all(len(it.unresolved_gt8) == 1 for it in outcome.iterations)


def test_execution_failure_blocks_pass():
    controller = AuditController(
        auditor=lambda model: [],  # no static finding
        executor=lambda model: _fail_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        max_iterations=3,
    )
    outcome = controller.run(_model())
    assert outcome.status == FAILED
    # the sev-10 execution finding is folded in and blocks the findings gate
    assert any(f.category == "execution" for f in outcome.final_findings)


def test_qa_failure_blocks_pass():
    controller = AuditController(
        auditor=lambda model: [],
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _fail_qa(),
        max_iterations=3,
    )
    outcome = controller.run(_model())
    assert outcome.status == FAILED


def test_patch_induced_regression_blocks_pass():
    # A patch that INTRODUCES a new severity>8 finding (different signature)
    # is tagged regression and blocks PASS via the independent regression gate.
    model_v1 = NotebookModel()
    model_v2 = NotebookModel(configuration={"patched": True})
    finding_a = _finding(cell="c1")
    finding_b = _finding(cell="c2")  # different location → different signature

    def auditor(model):
        return [finding_b if model is model_v2 else finding_a]

    def patcher(unresolved, model, prior):
        return PatchOutcome(model=model_v2, corrections={finding_a.id: "fix"})

    controller = AuditController(
        auditor=auditor,
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        patcher=patcher,
        max_iterations=2,
    )
    outcome = controller.run(model_v1)

    assert outcome.status == FAILED
    regressions = outcome.iterations[1].regressions
    assert len(regressions) == 1
    assert regressions[0].regression is True
    assert regressions[0].signature == finding_b.signature


# --------------------------------------------------------------------------- #
# max-iterations override (config + constructor)
# --------------------------------------------------------------------------- #
def test_max_iterations_config_override():
    config = AuditConfig()
    config.audit.max_iterations = 2
    controller = AuditController(
        config=config,
        auditor=lambda model: [_finding()],
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
    )
    outcome = controller.run(_model())
    assert outcome.max_iterations == 2
    assert len(outcome.iterations) == 2
    assert outcome.status == FAILED


def test_max_iterations_constructor_override():
    controller = AuditController(
        auditor=lambda model: [_finding()],
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        max_iterations=1,
    )
    outcome = controller.run(_model())
    assert outcome.max_iterations == 1
    assert len(outcome.iterations) == 1


def test_default_max_iterations_is_ten():
    controller = AuditController()
    assert controller.max_iterations == 10


# --------------------------------------------------------------------------- #
# Finding lifecycle + recurrence
# --------------------------------------------------------------------------- #
def _patcher(candidates: dict[str, list[str]]):
    """A patcher that offers the next not-yet-attempted correction per signature."""

    def patch(unresolved, model, prior):
        corrections: dict[str, str] = {}
        for finding in unresolved:
            attempted = prior.get(finding.signature, [])
            for candidate in candidates.get(finding.signature, []):
                if candidate not in attempted:
                    corrections[finding.id] = candidate
                    break
        return PatchOutcome(model=model, corrections=corrections)

    return patch


def test_recurring_issue_is_detected_and_fails():
    def auditor(model):
        return [_finding()]  # same signature every iteration

    controller = AuditController(
        auditor=auditor,
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        patcher=_patcher({}),  # empty candidates → never fixes
        max_iterations=3,
    )
    outcome = controller.run(_model())

    assert outcome.status == FAILED
    # recurring is detected from the 2nd iteration onward
    assert len(outcome.iterations[1].recurring) == 1
    assert len(outcome.iterations[2].recurring) == 1


def test_materially_different_correction_is_applied_repeat_is_rejected():
    # two candidate corrections: A (iter1), B (iter2, materially different);
    # iter3 offers nothing new → keeps failing (§20: never blindly repeat).
    controller = AuditController(
        auditor=lambda model: [_finding()],
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        patcher=_patcher({LEAK_SIG: ["fix A", "fix B"]}),
        max_iterations=3,
    )
    outcome = controller.run(_model())

    assert outcome.status == FAILED
    assert controller._attempted_corrections[LEAK_SIG] == ["fix A", "fix B"]
    # the iteration-1 finding (patched, then recurred) is marked RECURRING
    assert controller.history[0].status is Status.RECURRING
    # the prior-failure reason was recorded for the recurring signature
    assert LEAK_SIG in controller._failure_reasons
    assert "did not eliminate the root cause" in controller._failure_reasons[LEAK_SIG]
    # only two corrections recorded — nothing new was blindly repeated on iter3
    assert len(controller._attempted_corrections[LEAK_SIG]) == 2


def test_resolved_when_signature_disappears():
    calls = {"n": 0}

    def auditor(model):
        calls["n"] += 1
        # finding only on the first audit; the patch "fixes" it.
        return [_finding()] if calls["n"] == 1 else []

    controller = AuditController(
        auditor=auditor,
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        patcher=_patcher({LEAK_SIG: ["fix A"]}),
        max_iterations=3,
    )
    outcome = controller.run(_model())

    assert outcome.status == PASS
    # the iteration-1 finding (patched, then its signature vanished) is resolved
    assert controller.history[0].status is Status.RESOLVED
    assert len(outcome.iterations) == 2


# --------------------------------------------------------------------------- #
# wont_fix — user-only terminal, non-blocking
# --------------------------------------------------------------------------- #
def test_wont_fix_is_non_blocking_and_never_auto_assigned():
    controller = AuditController(
        auditor=lambda model: [_finding()],  # fresh finding, stable signature
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        max_iterations=3,
    )
    controller.mark_wont_fix(LEAK_SIG)

    outcome = controller.run(_model())

    # wont_fix is non-blocking → the finding does not prevent PASS
    assert outcome.status == PASS
    assert all(f.status is Status.WONT_FIX for f in controller.history)


# --------------------------------------------------------------------------- #
# Outcome serialization
# --------------------------------------------------------------------------- #
def test_outcome_round_trips_to_raw():
    controller = AuditController(
        auditor=lambda model: [_finding()],
        executor=lambda model: _ok_exec(),
        qa=lambda model, exec_result: _ok_qa(),
        max_iterations=2,
    )
    outcome = controller.run(_model())
    raw = outcome.to_raw()
    assert raw["status"] == FAILED
    assert raw["max_iterations"] == 2
    assert len(raw["iterations"]) == 2
    assert raw["iterations"][0]["iteration"] == 1
    assert "final_findings" in raw


def test_iteration_record_serializes_findings():
    record = IterationRecord(iteration=1, findings=[_finding()])
    raw = record.to_raw()
    assert raw["iteration"] == 1
    assert len(raw["findings"]) == 1
    assert raw["findings"][0]["category"] == "leakage"


# --------------------------------------------------------------------------- #
# LLM outage can never flip PASS/FAIL — semantic auditing is additive-only
# --------------------------------------------------------------------------- #
def _tiny_model() -> NotebookModel:
    import json

    from nb_audit.ir import NotebookParser

    return NotebookParser().parse(json.dumps({
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "id": "c1",
                "source": ["x = 1\n"],
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }))


def test_default_auditor_is_static_only_without_backend():
    controller = AuditController()
    findings = controller._default_auditor(_tiny_model())
    # `x = 1` is clean: no static finding, and no semantic signal (no backend).
    assert findings == []


def test_default_auditor_with_mock_backend_offline_adds_advisory_findings():
    from nb_audit.semantic.mock import MockBackend

    controller = AuditController(backend=MockBackend())
    findings = controller._default_auditor(_tiny_model())
    # the offline mock backend adds its deterministic schema-valid findings
    # (severity-9 metrics + severity-8 conclusions) — never a live LLM.
    assert any(f.category == "metrics" and f.severity == 9 for f in findings)
    assert any(f.category == "conclusions" and f.severity == 8 for f in findings)
