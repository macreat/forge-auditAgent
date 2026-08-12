"""Deterministic runtime ML QA checks (splits, tensors, metrics, checkpoints, artifacts)."""

from __future__ import annotations

from nb_audit.mlqa.check_registry import RuntimeCheck, RuntimeCheckRegistry

__all__ = ["RuntimeCheck", "RuntimeCheckRegistry", "default_registry"]


def default_registry() -> RuntimeCheckRegistry:
    """Return a registry with the built-in runtime ML QA checks pre-registered."""
    from nb_audit.mlqa.artifacts import ArtifactsCheck
    from nb_audit.mlqa.checkpoints import CheckpointsCheck
    from nb_audit.mlqa.metrics import MetricCheck
    from nb_audit.mlqa.splits import SplitCheck
    from nb_audit.mlqa.tensors import TensorCheck

    registry = RuntimeCheckRegistry()
    registry.register(SplitCheck)
    registry.register(TensorCheck)
    registry.register(MetricCheck)
    registry.register(CheckpointsCheck)
    registry.register(ArtifactsCheck)
    return registry
