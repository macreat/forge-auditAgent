"""Tests for nb_audit.mlqa.check_registry (RuntimeCheck ABC + registry) and __init__."""

from __future__ import annotations

import json

from nb_audit.ir import NotebookParser
from nb_audit.mlqa import default_registry
from nb_audit.mlqa.check_registry import RuntimeCheck, RuntimeCheckRegistry


def _model(source: str):
    raw = json.dumps({
        "cells": [{
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "id": "c1",
            "source": source,
        }],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    })
    return NotebookParser().parse(raw)


def test_default_registry_registers_all_five_checks():
    registry = default_registry()
    assert registry.names() == (
        "splits", "tensors", "metrics", "checkpoints", "artifacts",
    )
    for name in registry.names():
        assert issubclass(registry.get(name), RuntimeCheck)


def test_registry_run_assigns_stable_ids():
    model = _model("accuracy = 1.5\n")  # out-of-range metric
    registry = default_registry()
    findings = registry.run_all(model, {"accuracy": 1.5})
    assert findings
    ids = [f.id for f in findings]
    assert ids[0].startswith("metrics-")
    assert ids[0] == "metrics-01"


def test_registry_run_alias_matches_run_all():
    model = _model("")
    registry = default_registry()
    assert registry.run(model, {}) == registry.run_all(model, {})


def test_unknown_check_raises_key_error():
    registry = default_registry()
    try:
        registry.dispatch("nope", _model(""), {})
    except KeyError:
        return
    raise AssertionError("expected KeyError for unknown check")


def test_empty_namespace_yields_no_findings():
    registry = default_registry()
    assert registry.run_all(_model("x = 1\n"), {}) == []


def test_default_registry_is_deterministic():
    model = _model("accuracy = 1.5\ntrain_ids = [1, 2, 3]\nval_ids = [2, 3, 4]\n")
    ctx = {"accuracy": 1.5, "train_ids": [1, 2, 3], "val_ids": [2, 3, 4]}
    registry = default_registry()
    first = [f.to_raw() for f in registry.run_all(model, dict(ctx))]
    second = [f.to_raw() for f in registry.run_all(model, dict(ctx))]
    assert first == second
