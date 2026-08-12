"""Semantic LLM auditor backend: the :class:`Backend` ABC plus strict validation.

Design contract (spec §14 + design doc): the semantic auditor is a
strictly-degraded, ADVISORY signal. Its findings can only ever ADD to the
static/ML-QA findings, never remove them, and an LLM outage or malformed
response must NEVER turn a PASS into FAIL — the pipeline degrades to
static-only findings (an empty finding list) instead of raising.

The ABC exposes:

* ``render_prompt(ir)`` — builds the structured audit prompt (shared).
* ``validate_findings(payload)`` — strict JSON decode + per-field schema check.
  Pure, synchronous, and NEVER raises: invalid payloads yield ``[]``.
* ``audit(ir)`` — render → generate → validate, retrying with exponential
  backoff up to ``max_retries`` (default 2). On persistent failure (malformed
  JSON, schema violation, or transport/LLM exception) it returns ``[]``
  (static-only) and never raises.
* ``_generate(prompt)`` — the only abstract method: the actual LLM/network call.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any

from nb_audit.ir import NotebookModel
from nb_audit.models import Classification, Finding, Location
from nb_audit.semantic.prompts import render_audit_prompt

# Required fields for a semantic finding on the wire. ``severity`` must be a
# numeric type, ``category``/``issue`` must be non-empty strings. Everything
# else is optional with a documented default.
_REQUIRED_FIELDS = ("severity", "category", "issue")


class Backend(ABC):
    """Abstract semantic auditor backend.

    Concrete backends implement only :meth:`_generate`; prompt rendering and
    strict validation/retry logic are shared. All public methods are
    exception-safe: they degrade to an empty finding list rather than raise.
    """

    def __init__(self, max_retries: int = 2, backoff_seconds: float = 1.0) -> None:
        self.max_retries = max(0, int(max_retries))
        self.backoff_seconds = float(backoff_seconds)

    # -- prompt ------------------------------------------------------------ #
    def render_prompt(self, ir: NotebookModel) -> str:
        """Build the structured audit prompt for ``ir`` (shared across backends)."""
        return render_audit_prompt(ir)

    # -- generation (the only extension point) ----------------------------- #
    @abstractmethod
    async def _generate(self, prompt: str) -> str:
        """Return the raw LLM response text for ``prompt``.

        Implementations make the real network/LLM call (or return deterministic
        output for mocks). Any exception is caught by :meth:`audit` and treated
        as a failed attempt (degrade, never propagate).
        """

    # -- backoff ----------------------------------------------------------- #
    async def _sleep(self, delay: float) -> None:
        """Sleep ``delay`` seconds. Overridable so tests can observe backoff."""
        await asyncio.sleep(delay)

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff for the Nth retry (attempt >= 1)."""
        return self.backoff_seconds * (2 ** (attempt - 1))

    # -- validation -------------------------------------------------------- #
    def validate_findings(self, payload: str) -> list[Finding]:
        """Strictly parse and schema-validate ``payload``. Never raises.

        Returns the list of parsed :class:`Finding` objects on success, or an
        empty list on any malformed JSON or schema violation (the semantic
        signal is dropped and the pipeline degrades to static-only).
        """
        findings = self._parse_findings(payload)
        return findings if findings is not None else []

    @staticmethod
    def _extract_json(payload: str) -> Any:
        """Decode ``payload`` as JSON, tolerating an optional markdown fence."""
        text = payload.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return json.loads(text)

    @classmethod
    def _parse_findings(cls, payload: str) -> list[Finding] | None:
        """Strict parse + schema validation. ``None`` on any failure (no raise)."""
        if not isinstance(payload, str) or not payload.strip():
            return None
        try:
            data = cls._extract_json(payload)
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

        if isinstance(data, dict):
            raw_list = data.get("findings")
        elif isinstance(data, list):
            raw_list = data
        else:
            return None
        if not isinstance(raw_list, list):
            return None

        findings: list[Finding] = []
        for item in raw_list:
            finding = cls._validate_item(item)
            if finding is None:
                # Strict all-or-nothing: one invalid entry rejects the payload.
                return None
            findings.append(finding)
        return findings

    @staticmethod
    def _validate_item(item: Any) -> Finding | None:
        """Validate one finding entry against the wire schema. ``None`` if invalid."""
        if not isinstance(item, dict):
            return None
        severity = item.get("severity")
        category = item.get("category")
        issue = item.get("issue")
        if isinstance(severity, bool) or not isinstance(severity, (int, float)):
            return None
        if not isinstance(category, str) or not category.strip():
            return None
        if not isinstance(issue, str) or not issue.strip():
            return None

        location = item.get("location") or {}
        if not isinstance(location, dict):
            return None
        cell = location.get("cell", "")
        line = location.get("line")
        if not isinstance(cell, str):
            return None
        if line is not None and not isinstance(line, int):
            return None

        try:
            return Finding(
                id=str(item.get("id") or ""),
                severity=int(severity),
                classification=item.get("classification", Classification.NEW),
                category=category,
                location=Location(cell=cell, line=line),
                issue=issue,
                root_cause=str(item.get("root_cause") or ""),
                impact=str(item.get("impact") or ""),
                correction=str(item.get("correction") or ""),
                status=item.get("status", "unresolved"),
                signature=str(item.get("signature") or ""),
                patch_ids=list(item.get("patch_ids") or []),
            )
        except (ValueError, TypeError):
            return None

    # -- orchestration ----------------------------------------------------- #
    async def audit(self, ir: NotebookModel) -> list[Finding]:
        """Render → generate → validate, retrying with backoff up to max_retries.

        Retries the LLM call on malformed JSON, schema violation, or transport
        exception. After ``max_retries`` retries the semantic signal is
        REJECTED: the method returns ``[]`` (static-only) and NEVER raises, so
        an LLM outage can never flip a PASS into a FAIL.
        """
        prompt = self.render_prompt(ir)
        attempts = self.max_retries + 1  # one initial attempt + N retries
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                await self._sleep(self._backoff_delay(attempt - 1))
            try:
                payload = await self._generate(prompt)
            except Exception:
                payload = ""  # transport/LLM outage → treat as invalid attempt
            findings = self._parse_findings(payload)
            if findings is not None:
                return findings
        return []
