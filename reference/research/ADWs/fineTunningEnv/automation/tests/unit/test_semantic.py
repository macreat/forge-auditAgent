"""Tests for nb_audit.semantic (backend ABC, prompt, httpx + mock backends).

All tests are LLM-free and CPU-fast (REQ-016). The core invariant under test:
the semantic LLM auditor is ADVISORY — malformed JSON, schema violations, and
LLM outages degrade to static-only (an empty finding list) and NEVER raise, so
an outage can never flip a PASS into a FAIL.
"""

from __future__ import annotations

import asyncio
import json

import httpx

from nb_audit.config import AuditConfig
from nb_audit.ir import NotebookParser
from nb_audit.models import Finding
from nb_audit.semantic.backend import Backend
from nb_audit.semantic.mock import MOCK_FINDINGS, MockBackend
from nb_audit.semantic.openai_httpx import HttpxOpenAIBackend
from nb_audit.semantic.prompts import (
    AUDIT_CATEGORIES,
    category_keys,
    render_audit_prompt,
)


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
def _model(source: str = "import pandas as pd\n"):
    raw = json.dumps({
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "id": "c1",
                "source": source,
            },
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": "# Our model is state of the art",
                "id": "c2",
            },
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    })
    return NotebookParser().parse(raw)


def _valid_payload() -> str:
    return json.dumps({
        "findings": [
            {
                "severity": 9,
                "category": "metrics",
                "issue": "Metric mismatch",
                "location": {"cell": "c1", "line": 1},
                "root_cause": "selection metric differs",
                "impact": "misleading",
                "correction": "align metrics",
            },
        ]
    })


class _FakeBackend(Backend):
    """Backend whose responses are scripted and whose sleeps are recorded."""

    def __init__(self, responses, max_retries=2, backoff_seconds=1.0):
        super().__init__(max_retries=max_retries, backoff_seconds=backoff_seconds)
        self.responses = list(responses)
        self.calls = 0
        self.sleeps: list[float] = []

    async def _generate(self, prompt: str) -> str:
        self.calls += 1
        response = self.responses.pop(0) if self.responses else self.responses[-1]
        if isinstance(response, Exception):
            raise response
        return response

    async def _sleep(self, delay: float) -> None:
        self.sleeps.append(delay)


# --------------------------------------------------------------------------- #
# T-24: prompts — category map
# --------------------------------------------------------------------------- #
def test_category_map_has_exactly_15_categories():
    assert len(AUDIT_CATEGORIES) == 15
    assert len(category_keys()) == 15
    assert len(set(category_keys())) == 15  # keys are unique


def test_category_map_matches_spec_sections():
    sections = [c.section for c in AUDIT_CATEGORIES]
    assert sections == [f"6.{i}" for i in range(1, 16)]


def test_prompt_template_references_all_15_categories():
    prompt = render_audit_prompt(_model())
    for category in AUDIT_CATEGORIES:
        assert category.name in prompt
        assert category.section in prompt
        assert category.key in prompt


def test_prompt_is_deterministic():
    model = _model()
    assert render_audit_prompt(model) == render_audit_prompt(model)


def test_prompt_includes_ir_summary():
    prompt = render_audit_prompt(_model("pd.read_csv('data.csv')\n"))
    assert "pd.read_csv" in prompt
    assert "state of the art" in prompt


# --------------------------------------------------------------------------- #
# T-22: backend — strict JSON + schema validation
# --------------------------------------------------------------------------- #
def test_validate_findings_parses_valid_payload():
    backend = MockBackend()
    findings = backend.validate_findings(_valid_payload())
    assert len(findings) == 1
    finding = findings[0]
    assert isinstance(finding, Finding)
    assert finding.severity == 9
    assert finding.category == "metrics"
    assert finding.issue == "Metric mismatch"
    assert finding.location.cell == "c1"
    assert finding.location.line == 1


def test_validate_findings_rejects_malformed_json():
    backend = MockBackend()
    assert backend.validate_findings("not json {") == []
    assert backend.validate_findings("") == []
    assert backend.validate_findings("   ") == []


def test_validate_findings_rejects_non_object_non_list():
    backend = MockBackend()
    assert backend.validate_findings(json.dumps({"nope": 1})) == []
    assert backend.validate_findings(json.dumps("just a string")) == []


def test_validate_findings_rejects_missing_required_field():
    backend = MockBackend()
    payload = json.dumps({"findings": [{"category": "metrics", "issue": "x"}]})
    assert backend.validate_findings(payload) == []


def test_validate_findings_rejects_wrong_severity_type():
    backend = MockBackend()
    payload = json.dumps({
        "findings": [{"severity": "high", "category": "metrics", "issue": "x"}]
    })
    assert backend.validate_findings(payload) == []


def test_validate_findings_rejects_boolean_severity():
    backend = MockBackend()
    payload = json.dumps({
        "findings": [{"severity": True, "category": "metrics", "issue": "x"}]
    })
    assert backend.validate_findings(payload) == []


def test_validate_findings_rejects_one_invalid_item_all_or_nothing():
    backend = MockBackend()
    payload = json.dumps({
        "findings": [
            {"severity": 9, "category": "metrics", "issue": "ok"},
            {"severity": "bad", "category": "metrics", "issue": "bad"},
        ]
    })
    assert backend.validate_findings(payload) == []


def test_validate_findings_accepts_fenced_json():
    backend = MockBackend()
    fenced = "```json\n" + _valid_payload() + "\n```"
    findings = backend.validate_findings(fenced)
    assert len(findings) == 1


def test_validate_findings_never_raises_on_garbage():
    backend = MockBackend()
    assert backend.validate_findings(None) == []  # type: ignore[arg-type]
    assert backend.validate_findings(b"\x00\xff") == []  # type: ignore[arg-type]
    assert backend.validate_findings(json.dumps({"findings": "notalist"})) == []


def test_validate_findings_accepts_bare_list_and_empty_findings():
    backend = MockBackend()
    assert backend.validate_findings("[]") == []
    assert backend.validate_findings(json.dumps({"findings": []})) == []


# --------------------------------------------------------------------------- #
# T-22: retry-with-backoff + degrade to static-only
# --------------------------------------------------------------------------- #
def test_audit_retries_malformed_up_to_max_retries_then_degrades():
    backend = _FakeBackend(responses=["not json {"] * 10, max_retries=2)
    findings = asyncio.run(backend.audit(_model()))
    assert findings == []  # static-only, never raised
    assert backend.calls == 3  # 1 initial + 2 retries
    assert len(backend.sleeps) == 2


def test_audit_recovers_on_second_attempt():
    backend = _FakeBackend(responses=["not json {", _valid_payload()], max_retries=2)
    findings = asyncio.run(backend.audit(_model()))
    assert len(findings) == 1
    assert backend.calls == 2
    assert len(backend.sleeps) == 1


def test_audit_backoff_delays_follow_exponential_growth():
    backend = _FakeBackend(
        responses=["not json {"] * 10, max_retries=3, backoff_seconds=2.0
    )
    asyncio.run(backend.audit(_model()))
    assert backend.sleeps == [2.0, 4.0, 8.0]  # 2^0, 2^1, 2^2 scaled


def test_audit_degrades_to_static_only_on_llm_outage():
    backend = _FakeBackend(responses=[RuntimeError("outage")] * 10, max_retries=2)
    findings = asyncio.run(backend.audit(_model()))
    assert findings == []  # outage never raises, never flips PASS/FAIL
    assert backend.calls == 3


def test_audit_degrades_immediately_when_max_retries_is_zero():
    backend = _FakeBackend(responses=["not json {"], max_retries=0)
    findings = asyncio.run(backend.audit(_model()))
    assert findings == []
    assert backend.calls == 1
    assert backend.sleeps == []


# --------------------------------------------------------------------------- #
# T-25: MockBackend — deterministic schema-valid findings
# --------------------------------------------------------------------------- #
def test_mock_backend_findings_validate_against_schema():
    backend = MockBackend()
    findings = backend.validate_findings(backend.payload())
    assert len(findings) == len(MOCK_FINDINGS)
    assert all(isinstance(f, Finding) for f in findings)
    assert [f.category for f in findings] == ["metrics", "conclusions"]


def test_mock_backend_audit_round_trip_is_deterministic():
    model = _model()
    backend = MockBackend()
    first = [f.to_raw() for f in asyncio.run(backend.audit(model))]
    second = [f.to_raw() for f in asyncio.run(backend.audit(model))]
    assert first == second
    assert len(first) == len(MOCK_FINDINGS)


def test_mock_backend_render_generate_validate_round_trip():
    backend = MockBackend()
    prompt = backend.render_prompt(_model())
    payload = asyncio.run(backend._generate(prompt))
    findings = backend.validate_findings(payload)
    assert findings == asyncio.run(backend.audit(_model()))


# --------------------------------------------------------------------------- #
# T-23: HttpxOpenAIBackend — mock httpx transport
# --------------------------------------------------------------------------- #
def _chat_response(content: str) -> httpx.Response:
    body = {"choices": [{"message": {"content": content}}]}
    return httpx.Response(200, json=body)


def test_httpx_backend_returns_parsed_findings_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        return _chat_response(_valid_payload())

    backend = HttpxOpenAIBackend(
        base_url="http://fake",
        model="test-model",
        transport=httpx.MockTransport(handler),
        backoff_seconds=0.0,
    )
    findings = asyncio.run(backend.audit(_model()))
    assert len(findings) == 1
    assert findings[0].category == "metrics"


def test_httpx_backend_sends_model_and_prompt_in_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return _chat_response(_valid_payload())

    backend = HttpxOpenAIBackend(
        base_url="http://fake",
        model="test-model",
        transport=httpx.MockTransport(handler),
        backoff_seconds=0.0,
    )
    asyncio.run(backend.audit(_model()))
    body = captured["json"]
    assert body["model"] == "test-model"
    assert body["messages"][0]["content"]  # prompt embedded
    assert "audit categories" in body["messages"][0]["content"].lower()


def test_httpx_backend_from_config_reads_llm_section():
    config = AuditConfig.from_raw({
        "llm": {"base_url": "http://cfg", "model": "cfg-model", "max_retries": 3}
    })
    backend = HttpxOpenAIBackend.from_config(config, backoff_seconds=0.0)
    assert backend.base_url == "http://cfg"
    assert backend.model == "cfg-model"
    assert backend.max_retries == 3


def test_httpx_backend_env_fallback(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://env")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    backend = HttpxOpenAIBackend()
    assert backend.base_url == "http://env"
    assert backend.model == "env-model"


def test_httpx_backend_degrades_when_transport_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    backend = HttpxOpenAIBackend(
        base_url="http://fake",
        model="m",
        transport=httpx.MockTransport(handler),
        max_retries=1,
        backoff_seconds=0.0,
    )
    findings = asyncio.run(backend.audit(_model()))
    assert findings == []
