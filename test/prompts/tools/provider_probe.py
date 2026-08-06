#!/usr/bin/env python3
"""Ad-hoc provider probe: assert request shape and error hygiene per provider.

Runs offline with ``httpx.MockTransport`` canned responses — no real
endpoint, no test framework (strict TDD inactive). It asserts:

- URL, headers, and request body shape for local/openai/anthropic/ollama
- ``create_provider`` dispatch, ``ollamaModel`` fallback, missing-key errors
- provider errors are sanitized (API keys never leak into messages)
- per-request timeout default is 60s

Usage:
    cd test/prompts
    python3 tools/provider_probe.py

Exit code 0 when all checks pass, 1 otherwise.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

# Allow running as a plain script from anywhere: `python3 tools/provider_probe.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.utils import (
    AnthropicProvider,
    LocalLlamaProvider,
    OpenAIProvider,
    OllamaProvider,
    ProviderError,
    create_provider,
    mask_secret,
)

OPENAI_KEY = "sk-test-openai-key-1234"
ANTHROPIC_KEY = "sk-ant-test-key-5678"

RESULTS = []


def check(name, condition, detail=""):
    """Record a single probe check."""
    RESULTS.append((name, bool(condition)))
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def canned(handler):
    """Wrap a request handler so the probe can inspect the request."""
    captured = {}

    async def capture(request):
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return handler(request)

    return captured, httpx.MockTransport(capture)


SECTION_HEADER = "Data Ingestion"
SECTION_INSTRUCTIONS = "Write the section following the strict format."
SOURCE_CONTEXT = "SOURCE MARKDOWN CONTENT"


async def probe_local():
    captured, transport = canned(
        lambda req: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "===MARKDOWN===\nLocal draft."}}]},
        )
    )
    provider = LocalLlamaProvider(host="127.0.0.1", port=8000, transport=transport)
    text = await provider.draft_section(
        SECTION_HEADER, SECTION_INSTRUCTIONS, SOURCE_CONTEXT
    )
    check(
        "local: url is llama.cpp OpenAI-compatible endpoint",
        captured["url"] == "http://127.0.0.1:8000/v1/chat/completions",
        captured["url"],
    )
    check("local: no model field in payload", "model" not in captured["payload"])
    messages = captured["payload"]["messages"]
    check(
        "local: system instructions + user header/source",
        messages[0]["role"] == "system"
        and messages[0]["content"] == SECTION_INSTRUCTIONS
        and messages[1]["role"] == "user"
        and f"Section: {SECTION_HEADER}" in messages[1]["content"]
        and SOURCE_CONTEXT in messages[1]["content"],
    )
    check("local: text extracted", text.startswith("===MARKDOWN==="), text[:20])


async def probe_openai():
    captured, transport = canned(
        lambda req: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "===MARKDOWN===\nOpenAI draft."}}]},
        )
    )
    provider = OpenAIProvider(api_key=OPENAI_KEY, transport=transport)
    text = await provider.draft_section(
        SECTION_HEADER, SECTION_INSTRUCTIONS, SOURCE_CONTEXT
    )
    check(
        "openai: url is chat completions",
        captured["url"] == "https://api.openai.com/v1/chat/completions",
        captured["url"],
    )
    check(
        "openai: bearer auth header",
        captured["headers"].get("authorization") == f"Bearer {OPENAI_KEY}",
    )
    check(
        "openai: default model in payload",
        captured["payload"]["model"] == OpenAIProvider.DEFAULT_MODEL,
        captured["payload"]["model"],
    )
    check(
        "openai: key never in prompt content",
        OPENAI_KEY not in json.dumps(captured["payload"]["messages"]),
    )
    check("openai: text extracted", text.startswith("===MARKDOWN==="))

    # Error hygiene: HTTP 401 must raise ProviderError without leaking the key.
    def failing(request):
        return httpx.Response(401, json={"error": {"message": f"bad key {OPENAI_KEY}"}})

    provider = OpenAIProvider(api_key=OPENAI_KEY, transport=httpx.MockTransport(failing))
    try:
        await provider.draft_section(SECTION_HEADER, SECTION_INSTRUCTIONS, SOURCE_CONTEXT)
        check("openai: http error raises ProviderError", False)
    except ProviderError as exc:
        msg = str(exc)
        check("openai: http error raises ProviderError", True)
        check("openai: error message hides key and body", OPENAI_KEY not in msg and "401" in msg, msg)


async def probe_anthropic():
    captured, transport = canned(
        lambda req: httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "===MARKDOWN===\nAnthropic draft."}
                ]
            },
        )
    )
    provider = AnthropicProvider(api_key=ANTHROPIC_KEY, transport=transport)
    text = await provider.draft_section(
        SECTION_HEADER, SECTION_INSTRUCTIONS, SOURCE_CONTEXT
    )
    check(
        "anthropic: url is /v1/messages",
        captured["url"] == "https://api.anthropic.com/v1/messages",
        captured["url"],
    )
    check(
        "anthropic: x-api-key header",
        captured["headers"].get("x-api-key") == ANTHROPIC_KEY,
    )
    check(
        "anthropic: version header",
        captured["headers"].get("anthropic-version") == AnthropicProvider.API_VERSION,
    )
    check(
        "anthropic: system in separate field",
        captured["payload"]["system"] == SECTION_INSTRUCTIONS,
    )
    check(
        "anthropic: no system inside messages",
        "system" not in captured["payload"]["messages"][0]
        and captured["payload"]["messages"][0]["role"] == "user",
    )
    check(
        "anthropic: key never in prompt content",
        ANTHROPIC_KEY not in json.dumps(captured["payload"]),
    )
    check("anthropic: text extracted", text.startswith("===MARKDOWN==="))

    # Error hygiene: HTTP 403 must raise ProviderError without leaking the key.
    def failing(request):
        return httpx.Response(403, json={"error": {"message": f"key {ANTHROPIC_KEY}"}})

    provider = AnthropicProvider(api_key=ANTHROPIC_KEY, transport=httpx.MockTransport(failing))
    try:
        await provider.draft_section(SECTION_HEADER, SECTION_INSTRUCTIONS, SOURCE_CONTEXT)
        check("anthropic: http error raises ProviderError", False)
    except ProviderError as exc:
        msg = str(exc)
        check("anthropic: http error raises ProviderError", True)
        check("anthropic: error message hides key and body", ANTHROPIC_KEY not in msg and "403" in msg, msg)


async def probe_ollama():
    captured, transport = canned(
        lambda req: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "===MARKDOWN===\nOllama draft."}}]},
        )
    )
    provider = OllamaProvider(transport=transport)
    text = await provider.draft_section(
        SECTION_HEADER, SECTION_INSTRUCTIONS, SOURCE_CONTEXT
    )
    check(
        "ollama: url is localhost:11434",
        captured["url"] == "http://localhost:11434/v1/chat/completions",
        captured["url"],
    )
    check(
        "ollama: model fallback llama3.2",
        captured["payload"]["model"] == "llama3.2",
        captured["payload"]["model"],
    )
    check("ollama: text extracted", text.startswith("===MARKDOWN==="))

    captured2, transport2 = canned(
        lambda req: httpx.Response(
            200,
            json={"choices": [{"message": {"content": "===MARKDOWN===\nDraft."}}]},
        )
    )
    provider2 = OllamaProvider(model="llama3.1", transport=transport2)
    await provider2.draft_section(SECTION_HEADER, SECTION_INSTRUCTIONS, SOURCE_CONTEXT)
    check(
        "ollama: explicit model override",
        captured2["payload"]["model"] == "llama3.1",
        captured2["payload"]["model"],
    )


async def probe_errors():
    # Transport failure -> sanitized ProviderError.
    def dead(request):
        raise httpx.ConnectError("connection refused", request=request)

    provider = LocalLlamaProvider(transport=httpx.MockTransport(dead))
    try:
        await provider.draft_section(SECTION_HEADER, SECTION_INSTRUCTIONS, SOURCE_CONTEXT)
        check("transport failure raises ProviderError", False)
    except ProviderError as exc:
        msg = str(exc)
        check("transport failure raises ProviderError", True)
        check(
            "transport failure message sanitized",
            "could not reach" in msg and "connection refused" not in msg,
            msg,
        )

    # Default timeout is 60s (per-request timeout requirement).
    provider = LocalLlamaProvider()
    check("default per-request timeout is 60s", provider.timeout == 60.0)
    provider = OpenAIProvider(api_key=OPENAI_KEY)
    check("openai timeout default 60s", provider.timeout == 60.0)

    # Unparseable JSON -> ProviderError.
    captured, transport = canned(lambda req: httpx.Response(200, text="not-json"))
    provider = OllamaProvider(transport=transport)
    try:
        await provider.draft_section(SECTION_HEADER, SECTION_INSTRUCTIONS, SOURCE_CONTEXT)
        check("invalid JSON raises ProviderError", False)
    except ProviderError:
        check("invalid JSON raises ProviderError", True)


def probe_dispatch():
    provider = create_provider({"llmProvider": "local"})
    check("dispatch: local", isinstance(provider, LocalLlamaProvider))

    provider = create_provider({"llmProvider": "OpenAI", "openaiApiKey": OPENAI_KEY})
    check("dispatch: openai (case-insensitive)", isinstance(provider, OpenAIProvider))

    provider = create_provider({"llmProvider": "anthropic", "anthropicApiKey": ANTHROPIC_KEY})
    check("dispatch: anthropic", isinstance(provider, AnthropicProvider))

    provider = create_provider({"llmProvider": "ollama"})
    check("dispatch: ollama + model fallback", isinstance(provider, OllamaProvider) and provider.model == "llama3.2")

    provider = create_provider({"llmProvider": "ollama", "ollamaModel": "llama3.1"})
    check("dispatch: ollama custom model", isinstance(provider, OllamaProvider) and provider.model == "llama3.1")

    provider = create_provider({})
    check("dispatch: default is local", isinstance(provider, LocalLlamaProvider))

    try:
        create_provider({"llmProvider": "nope"})
        check("dispatch: unknown provider raises", False)
    except ProviderError as exc:
        check("dispatch: unknown provider raises", "nope" in str(exc))

    try:
        create_provider({"llmProvider": "openai"})
        check("dispatch: openai without key raises", False)
    except ProviderError:
        check("dispatch: openai without key raises", True)

    try:
        create_provider({"llmProvider": "anthropic"})
        check("dispatch: anthropic without key raises", False)
    except ProviderError:
        check("dispatch: anthropic without key raises", True)


def probe_mask_secret():
    check("mask_secret: long key", mask_secret("sk-abc12345") == "****2345")
    check("mask_secret: empty", mask_secret("") == "")
    check("mask_secret: short", mask_secret("ab") == "****")
    check("mask_secret: exactly visible", mask_secret("abcd") == "****")


async def main():
    print("== provider_probe ==")
    probe_dispatch()
    probe_mask_secret()
    await probe_local()
    await probe_openai()
    await probe_anthropic()
    await probe_ollama()
    await probe_errors()

    failed = [name for name, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("FAILED:")
        for name in failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
