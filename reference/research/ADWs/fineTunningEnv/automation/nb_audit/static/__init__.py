"""Deterministic, LLM-free static audit checks (syntax, AST, API misuse)."""

from __future__ import annotations

from nb_audit.static.check_registry import CheckRegistry, StaticCheck

__all__ = ["CheckRegistry", "StaticCheck", "default_registry"]


def default_registry() -> CheckRegistry:
    """Return a registry with the built-in static checks pre-registered."""
    from nb_audit.static.api_checks import ApiChecksCheck
    from nb_audit.static.ast_analysis import AstAnalysisCheck
    from nb_audit.static.syntax import SyntaxCheck

    registry = CheckRegistry()
    registry.register(SyntaxCheck)
    registry.register(AstAnalysisCheck)
    registry.register(ApiChecksCheck)
    return registry
