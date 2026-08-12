"""OpenAI-compatible HTTP backend for the semantic LLM auditor (httpx.AsyncClient).

Implements the single abstract hook :meth:`Backend._generate` with a
``httpx.AsyncClient`` POST to ``/chat/completions``. ``base_url`` and ``model``
resolve from explicit constructor arguments, then ``LLM_BASE_URL``/``LLM_MODEL``
environment variables; :meth:`from_config` wires them from the resolved
``AuditConfig.llm`` section (which already folds in ``NB_AUDIT_LLM_*`` env vars
via the config resolver). A ``transport`` argument (e.g. ``httpx.MockTransport``)
is accepted for deterministic tests with no live endpoint.
"""

from __future__ import annotations

import os

import httpx

from nb_audit.config import AuditConfig
from nb_audit.semantic.backend import Backend


class HttpxOpenAIBackend(Backend):
    """Semantic auditor backend backed by an OpenAI-compatible chat-completions API."""

    def __init__(
        self,
        base_url: str = "",
        model: str = "",
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
        temperature: float | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(max_retries=max_retries, backoff_seconds=backoff_seconds)
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "")
        self.temperature = temperature
        self.timeout = timeout
        self._transport = transport
        self._headers = dict(headers or {})

    @classmethod
    def from_config(cls, config: AuditConfig, **kwargs) -> "HttpxOpenAIBackend":
        """Build a backend from the resolved ``config.llm`` section.

        ``NB_AUDIT_LLM_BASE_URL`` / ``NB_AUDIT_LLM_MODEL`` env overrides are
        already applied by ``AuditConfig.load``; extra kwargs (e.g. ``transport``,
        ``timeout``) are forwarded to the constructor.
        """
        llm = config.llm
        return cls(
            base_url=llm.base_url,
            model=llm.model,
            max_retries=llm.max_retries,
            temperature=llm.temperature,
            **kwargs,
        )

    def _request_payload(self, prompt: str) -> dict:
        """Build the chat-completions request body for ``prompt``."""
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature if self.temperature is not None else 0.0,
            "response_format": {"type": "json_object"},
        }

    async def _generate(self, prompt: str) -> str:
        """POST ``/chat/completions`` and return the assistant message content."""
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self._transport,
            headers=self._headers,
        ) as client:
            response = await client.post("/chat/completions", json=self._request_payload(prompt))
            response.raise_for_status()
            data = response.json()

        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or ""
