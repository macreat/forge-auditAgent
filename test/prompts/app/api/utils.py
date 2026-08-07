"""LLM provider abstraction layer.

Unified asynchronous interface for drafting notebook sections through a
provider strategy. Each provider talks to a specific endpoint via
:mod:`httpx` and returns raw section text in the strict
``===MARKDOWN===`` / ``===CODE===`` format (see the ``llm-section-drafting``
spec). The active provider is selected by the ``llmProvider`` config key
through :func:`create_provider`.

Providers:
    - **local** — in-process llama.cpp OpenAI-compatible endpoint. Host and
      port reuse the ``AsyncLlamaServer`` contract from :mod:`app.api.local`
      (default ``127.0.0.1:8000``).
    - **openai** — OpenAI chat completions API (``openaiApiKey``).
    - **anthropic** — Anthropic Messages API ``/v1/messages`` with the
      ``x-api-key`` header and a separate ``system`` field
      (``anthropicApiKey``).
    - **ollama** — local Ollama server at ``localhost:11434``,
      OpenAI-compatible endpoint (model from ``ollamaModel``, fallback
      ``"llama3.2"``).

API keys are read from the passed config dict only; they are never logged
and never embedded in prompts. Every provider enforces a per-request
timeout and raises :class:`ProviderError` on transport, HTTP, or parse
failures, with sanitized messages that never leak keys or full request
bodies.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Mapping

import httpx


class ProviderError(Exception):
    """Raised when a provider request fails (transport, HTTP, or parse).

    Messages are sanitized: they never contain API keys, full request
    bodies, or response bodies.
    """


def mask_secret(secret: str, visible: int = 4) -> str:
    """Return a masked form of a secret suitable for UI display.

    Returns ``"****"`` plus the last ``visible`` characters, or an empty
    string for an empty secret. Used by the settings UI to render stored
    API keys.

    Args:
        secret: The value to mask (e.g. an API key).
        visible: Number of trailing characters to keep visible.

    Returns:
        The masked representation, or ``""`` when the secret is empty.
    """
    if not secret:
        return ""
    if len(secret) <= visible:
        return "****"
    return "****" + secret[-visible:]


def _format_source_prompt(header: str, source_context: str) -> str:
    """Compose the user message for one section draft.

    The drafting instructions go in the provider's system field; the
    canonical header and the source document content are user context.
    Config values (API keys, models) never appear in this message.
    """
    return f"Section: {header}\n\nSource content:\n{source_context}"


def _extract_openai_completion(data: Mapping[str, Any], provider_name: str) -> str:
    """Extract assistant text from an OpenAI-compatible completion response.

    Raises:
        ProviderError: If the response has no choices or empty content.
    """
    choices = data.get("choices") or []
    if not choices:
        raise ProviderError(f"{provider_name}: empty completion response")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content or not isinstance(content, str):
        raise ProviderError(f"{provider_name}: empty completion content")
    return content


def _extract_anthropic_text(data: Mapping[str, Any], provider_name: str) -> str:
    """Extract text from an Anthropic Messages API response.

    The Anthropic response carries text in ``content`` blocks with
    ``{"type": "text", "text": ...}``; all text blocks are concatenated.

    Raises:
        ProviderError: If the response contains no text blocks.
    """
    blocks = data.get("content") or []
    text = "".join(
        block.get("text", "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    )
    if not text:
        raise ProviderError(f"{provider_name}: empty completion response")
    return text


class LLMProvider(ABC):
    """Strategy interface for LLM drafting endpoints.

    Concrete providers implement :meth:`draft_section`, which returns the
    raw section text for one scaffold section. Failures raise
    :class:`ProviderError`; a provider request failure counts as a
    validation failure for the retry-once rule in the drafting pipeline.
    """

    DEFAULT_TIMEOUT = 60.0
    TEMPERATURE = 0.7
    MAX_TOKENS = 4096

    _name = "provider"
    _endpoint_desc = "endpoint"

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            timeout: Per-request timeout in seconds. Default 60s.
            transport: Optional ``httpx`` transport (used by ad-hoc probes
                to inject ``httpx.MockTransport`` canned responses).
        """
        self.timeout = timeout
        self._transport = transport

    @abstractmethod
    async def draft_section(
        self, header: str, instructions: str, source_context: str
    ) -> str:
        """Draft the content of a single notebook section.

        Args:
            header: Canonical section header (e.g. "Data Ingestion").
            instructions: Drafting instructions for this section.
            source_context: Source document content used as context only.

        Returns:
            Raw section text in the strict ``===MARKDOWN===`` /
            ``===CODE===`` format (see the llm-section-drafting spec).

        Raises:
            ProviderError: On transport, HTTP, or parse failure. The
                message never contains API keys or full request bodies.
        """

    async def _post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """POST JSON to a provider endpoint and return the JSON response.

        All failures are translated into :class:`ProviderError` with
        sanitized messages: no API keys, no request bodies, no response
        bodies.

        Raises:
            ProviderError: On timeout, transport failure, HTTP error, or
                unparseable JSON.
        """
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"{self._name}: request timed out after {self.timeout}s "
                f"({self._endpoint_desc})"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"{self._name}: HTTP {exc.response.status_code} "
                f"({self._endpoint_desc})"
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderError(
                f"{self._name}: could not reach {self._endpoint_desc}"
            ) from exc
        except ValueError as exc:
            raise ProviderError(
                f"{self._name}: invalid JSON response ({self._endpoint_desc})"
            ) from exc

    def _completion_payload(
        self, instructions: str, header: str, source_context: str
    ) -> dict[str, Any]:
        """Build the standard OpenAI-compatible chat completion body.

        The instructions go in the system message; header and source
        content go in the user message. No config values (keys, models)
        are embedded here.
        """
        return {
            "messages": [
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": _format_source_prompt(header, source_context),
                },
            ],
            "temperature": self.TEMPERATURE,
            "max_tokens": self.MAX_TOKENS,
        }


class LocalLlamaProvider(LLMProvider):
    """Draft through the app's in-process llama.cpp server.

    Talks to the OpenAI-compatible endpoint exposed by
    :class:`app.api.local.AsyncLlamaServer` at ``http://{host}:{port}``.
    The host/port contract matches the server's constructor arguments
    (default ``127.0.0.1:8000``) and the ``host``/``port`` settings keys.
    """

    _name = "local"
    _endpoint_desc = "local llama.cpp server"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        timeout: float = LLMProvider.DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(timeout=timeout, transport=transport)
        self.host = host
        self.port = port
        self._endpoint_desc = f"local llama.cpp server at {host}:{port}"

    async def draft_section(
        self, header: str, instructions: str, source_context: str
    ) -> str:
        url = f"http://{self.host}:{self.port}/v1/chat/completions"
        payload = self._completion_payload(instructions, header, source_context)
        data = await self._post_json(url, {}, payload)
        return _extract_openai_completion(data, self._name)


class OpenAIProvider(LLMProvider):
    """Draft through the OpenAI chat completions API."""

    DEFAULT_MODEL = "gpt-4o-mini"
    _name = "openai"
    _endpoint_desc = "OpenAI API"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = LLMProvider.DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("openai provider requires openaiApiKey in config")
        super().__init__(timeout=timeout, transport=transport)
        self._api_key = api_key
        self.model = model

    async def draft_section(
        self, header: str, instructions: str, source_context: str
    ) -> str:
        payload = self._completion_payload(instructions, header, source_context)
        payload["model"] = self.model
        headers = {"Authorization": f"Bearer {self._api_key}"}
        data = await self._post_json(
            "https://api.openai.com/v1/chat/completions", headers, payload
        )
        return _extract_openai_completion(data, self._name)


class AnthropicProvider(LLMProvider):
    """Draft through the Anthropic Messages API (``/v1/messages``).

    Uses the ``x-api-key`` header and sends the system prompt in the
    separate ``system`` field rather than inside ``messages``.
    """

    DEFAULT_MODEL = "claude-3-5-haiku-latest"
    API_VERSION = "2023-06-01"
    _name = "anthropic"
    _endpoint_desc = "Anthropic API"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = LLMProvider.DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("anthropic provider requires anthropicApiKey in config")
        super().__init__(timeout=timeout, transport=transport)
        self._api_key = api_key
        self.model = model

    async def draft_section(
        self, header: str, instructions: str, source_context: str
    ) -> str:
        payload = {
            "model": self.model,
            "max_tokens": self.MAX_TOKENS,
            "system": instructions,
            "messages": [
                {
                    "role": "user",
                    "content": _format_source_prompt(header, source_context),
                }
            ],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
        }
        data = await self._post_json(
            "https://api.anthropic.com/v1/messages", headers, payload
        )
        return _extract_anthropic_text(data, self._name)


class OllamaProvider(LLMProvider):
    """Draft through a local Ollama server (OpenAI-compatible endpoint).

    Defaults to ``http://localhost:11434``; the model comes from the
    ``ollamaModel`` config key with a ``"llama3.2"`` fallback.
    """

    _name = "ollama"
    _endpoint_desc = "Ollama server"

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        timeout: float = LLMProvider.DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(timeout=timeout, transport=transport)
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._endpoint_desc = f"Ollama server at {self.base_url}"

    async def draft_section(
        self, header: str, instructions: str, source_context: str
    ) -> str:
        payload = self._completion_payload(instructions, header, source_context)
        payload["model"] = self.model
        data = await self._post_json(
            f"{self.base_url}/v1/chat/completions", {}, payload
        )
        return _extract_openai_completion(data, self._name)


def create_provider(cfg: Mapping[str, Any]) -> LLMProvider:
    """Build the provider selected by the ``llmProvider`` config key.

    Args:
        cfg: Merged user settings dict (see
            :func:`app.config.settings.load`).

    Returns:
        The configured :class:`LLMProvider`.

    Raises:
        ProviderError: For an unknown provider name or a missing required
            API key for an external provider.
    """
    name = (cfg.get("llmProvider") or "local").strip().lower()
    if name == "local":
        return LocalLlamaProvider(
            host=cfg.get("host", "127.0.0.1"),
            port=int(cfg.get("port", 8000)),
        )
    if name == "openai":
        return OpenAIProvider(api_key=cfg.get("openaiApiKey", ""))
    if name == "anthropic":
        return AnthropicProvider(api_key=cfg.get("anthropicApiKey", ""))
    if name == "ollama":
        return OllamaProvider(model=cfg.get("ollamaModel") or "llama3.2")
    raise ProviderError(
        f"unknown llmProvider {name!r}; expected one of "
        "local, openai, anthropic, ollama"
    )
