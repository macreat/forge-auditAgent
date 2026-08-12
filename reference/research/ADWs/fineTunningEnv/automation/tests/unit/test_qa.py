"""Unit tests for nb_audit.qa — the runtime QA orchestration gate."""

from __future__ import annotations

from nb_audit.config import AuditConfig
from nb_audit.execute import ERROR, SUCCESS, ExecutionResult
from nb_audit.ir import NotebookParser
from nb_audit.mlqa import default_registry
from nb_audit.models import Classification, Finding, Location
from nb_audit.qa import FAILED, PASS, QAResult, RuntimeQA


def _model(source: str = ""):
    import json

    raw = json.dumps({
        "cells": [{
            "cell_type": "code",
            "id": "c1",
            "metadata": {},
            "outputs": [],
            "source": source,
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    })
    return NotebookParser().parse(raw)


def _exec_finding():
    return Finding(
        id="",
        severity=10,
        classification=Classification.NEW,
        category="execution",
        location=Location(cell="c1"),
        issue="Notebook execution failed",
        root_cause="boom",
    )


def _failed_exec():
    return ExecutionResult(status=ERROR, finding=_exec_finding())


def _ok_exec(namespace=None):
    return ExecutionResult(status=SUCCESS, namespace=namespace or {})


# -- the require_clean_execution gate ---------------------------------------- #
def test_exec_failure_blocks_qa_pass_when_gate_enabled():
    qa = RuntimeQA(config=AuditConfig())  # require_clean_execution=True by default
    result = qa.run(_model(), _failed_exec())
    assert result.status == FAILED
    assert result.passed is False
    assert len(result.findings) == 1
    assert result.findings[0].severity == 10
    assert result.findings[0].category == "execution"


def test_exec_failure_surfaces_exec_finding():
    qa = RuntimeQA(config=AuditConfig())
    result = qa.run(_model(), _failed_exec())
    assert result.findings[0].category == "execution"
    assert result.findings[0].severity == 10


def test_exec_failure_without_finding_still_fails():
    qa = RuntimeQA(config=AuditConfig())
    result = qa.run(_model(), ExecutionResult(status=ERROR))
    assert result.status == FAILED
    assert result.findings == []


def test_exec_failure_does_not_block_qa_when_gate_disabled():
    config = AuditConfig()
    config.qa.require_clean_execution = False
    qa = RuntimeQA(config=config)
    result = qa.run(_model(), _failed_exec())
    assert result.status == PASS
    # no exec finding surfaced because the gate is off; checks run over {} instead
    assert not any(f.category == "execution" for f in result.findings)


# -- clean execution --------------------------------------------------------- #
def test_clean_execution_yields_pass_with_no_findings():
    qa = RuntimeQA(config=AuditConfig())
    result = qa.run(_model(), _ok_exec())
    assert result.status == PASS
    assert result.findings == []


def test_clean_execution_surfaces_runtime_findings():
    # leaky splits on a clean execution still produce a severity-9 finding.
    qa = RuntimeQA(config=AuditConfig())
    result = qa.run(
        _model(),
        _ok_exec({"train_ids": [0, 1, 2], "val_ids": [1, 2, 3]}),
    )
    assert result.status == PASS
    assert any(f.category == "splits" and f.severity == 9 for f in result.findings)


def test_qa_result_passed_property():
    assert QAResult(PASS).passed is True
    assert QAResult(FAILED).passed is False


# -- registry wiring --------------------------------------------------------- #
def test_default_registry_has_all_five_checks():
    registry = default_registry()
    assert set(registry.names()) == {
        "splits", "tensors", "metrics", "checkpoints", "artifacts",
    }


def test_runtime_qa_uses_custom_registry():
    from nb_audit.mlqa.check_registry import RuntimeCheckRegistry
    from nb_audit.mlqa.splits import SplitCheck

    registry = RuntimeCheckRegistry()
    registry.register(SplitCheck)
    qa = RuntimeQA(config=AuditConfig(), registry=registry)
    result = qa.run(
        _model(),
        _ok_exec({"train_ids": [0, 1], "test_ids": [1, 2]}),
    )
    assert result.status == PASS
    assert any(f.category == "splits" for f in result.findings)
