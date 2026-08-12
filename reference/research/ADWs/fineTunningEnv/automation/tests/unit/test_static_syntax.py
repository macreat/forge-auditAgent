"""Tests for nb_audit.static.check_registry and nb_audit.static.syntax."""

from __future__ import annotations

from pathlib import Path

import pytest

from nb_audit.ir import NotebookModel, NotebookParser
from nb_audit.static.check_registry import CheckRegistry, StaticCheck
from nb_audit.static.syntax import SyntaxCheck

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _parse(name: str) -> NotebookModel:
    return NotebookParser().parse_file(str(FIXTURES / name))


# --------------------------------------------------------------------------- #
# Registry (T-10)
# --------------------------------------------------------------------------- #
class _DummyCheck(StaticCheck):
    name = "dummy"
    category = "dummy"
    severity = 3

    def check(self, model: NotebookModel):
        return []


def test_registry_registers_and_dispatches_new_check():
    registry = CheckRegistry()
    registry.register(_DummyCheck)
    model = _parse("tiny.ipynb")
    assert registry.get("dummy") is _DummyCheck
    assert registry.dispatch("dummy", model) == []
    assert registry.names() == ("dummy",)


def test_registry_rejects_check_without_name():
    class _Anonymous(StaticCheck):
        def check(self, model):  # pragma: no cover - never invoked
            return []

    registry = CheckRegistry()
    with pytest.raises(ValueError):
        registry.register(_Anonymous)


def test_registry_dispatch_unknown_name_raises():
    registry = CheckRegistry()
    with pytest.raises(KeyError):
        registry.dispatch("nope", _parse("tiny.ipynb"))


# --------------------------------------------------------------------------- #
# Syntax check (T-11)
# --------------------------------------------------------------------------- #
def test_syntax_error_fixture_yields_severity_10_finding():
    registry = CheckRegistry()
    registry.register(SyntaxCheck)
    findings = registry.run(_parse("syntax_error.ipynb"))
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == 10
    assert finding.category == "syntax"
    assert finding.location.cell == "code-broken"
    assert finding.location.line is not None
    assert "Syntax error" in finding.issue


def test_valid_notebook_has_no_syntax_findings():
    registry = CheckRegistry()
    registry.register(SyntaxCheck)
    assert registry.run(_parse("tiny.ipynb")) == []


def test_syntax_check_is_deterministic():
    registry = CheckRegistry()
    registry.register(SyntaxCheck)
    first = [f.to_raw() for f in registry.run(_parse("syntax_error.ipynb"))]
    second = [f.to_raw() for f in registry.run(_parse("syntax_error.ipynb"))]
    assert first == second
