"""Pluggable semantic LLM auditor (strictly-degraded optional signal).

Exposes the :class:`Backend` ABC and the built-in OpenAI-compatible and mock
implementations. Backends are imported lazily inside ``default_backend`` /
``mock_backend`` helpers to avoid pulling in ``httpx`` at package import time
(matching the static/mlqa package pattern).
"""

from __future__ import annotations

from nb_audit.semantic.backend import Backend

__all__ = [
    "Backend",
    "HttpxOpenAIBackend",
    "MockBackend",
    "mock_backend",
]


def mock_backend(**kwargs) -> "MockBackend":
    """Return a deterministic :class:`MockBackend` (offline, no network/LLM)."""
    from nb_audit.semantic.mock import MockBackend

    return MockBackend(**kwargs)
