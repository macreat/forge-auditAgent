"""Tests for nb_audit.mlqa.checkpoints (restoration + architecture/loss compat)."""

from __future__ import annotations

import json

from nb_audit.ir import NotebookParser
from nb_audit.mlqa.check_registry import RuntimeCheckRegistry
from nb_audit.mlqa.checkpoints import CheckpointsCheck


def _model(source: str = ""):
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


def _run(model, ctx):
    registry = RuntimeCheckRegistry()
    registry.register(CheckpointsCheck)
    return registry.run_all(model, ctx)


class FakeModel:
    """Minimal nn.Module double exposing ``state_dict()``."""

    def __init__(self, state):
        self._state = dict(state)

    def state_dict(self):
        return dict(self._state)


_SAVE_SOURCE = (
    "import torch\n"
    "model = Net()\n"
    "torch.save(model.state_dict(), 'best.pt')\n"
)

_LOAD_SOURCE = (
    "import torch\n"
    "checkpoint = torch.load('best.pt')\n"
    "model.load_state_dict(checkpoint)\n"
)


def test_saved_checkpoint_never_restored_yields_finding():
    model = _model(_SAVE_SOURCE)
    ctx = {"model": FakeModel({"weight": 0, "bias": 0})}
    findings = _run(model, ctx)
    restored = [f for f in findings if "never restored" in f.issue]
    assert len(restored) == 1
    assert restored[0].severity == 9
    assert restored[0].category == "checkpoints"


def test_load_claimed_without_checkpoint_yields_finding():
    model = _model(_LOAD_SOURCE)
    ctx = {"model": FakeModel({"weight": 0, "bias": 0})}
    findings = _run(model, ctx)
    claimed = [f for f in findings if "restoration claimed" in f.issue]
    assert len(claimed) == 1
    assert claimed[0].severity == 9


def test_restored_checkpoint_yields_no_restoration_finding():
    model = _model(_LOAD_SOURCE)
    ctx = {
        "model": FakeModel({"weight": 0, "bias": 0}),
        "checkpoint": {"weight": 0, "bias": 0},
    }
    findings = _run(model, ctx)
    assert not any("restored" in f.issue for f in findings)


def test_architecture_mismatch_yields_finding():
    model = _model(_LOAD_SOURCE)
    ctx = {
        "model": FakeModel({"weight": 0, "bias": 0}),
        "checkpoint": {"weight": 0, "bias": 0, "extra_layer": 0},
    }
    findings = _run(model, ctx)
    arch = [f for f in findings if "architecture mismatch" in f.issue]
    assert len(arch) == 1
    assert arch[0].severity == 9


def test_matching_architecture_yields_no_mismatch():
    model = _model(_LOAD_SOURCE)
    ctx = {
        "model": FakeModel({"weight": 0, "bias": 0}),
        "checkpoint": {"weight": 0, "bias": 0},
    }
    findings = _run(model, ctx)
    assert not any("architecture mismatch" in f.issue for f in findings)


def test_full_checkpoint_unwraps_wrapped_state_dict():
    model = _model(_LOAD_SOURCE)
    ctx = {
        "model": FakeModel({"weight": 0, "bias": 0}),
        "checkpoint": {
            "epoch": 5,
            "model_state_dict": {"weight": 0, "bias": 0},
            "best_loss": 0.1,
        },
    }
    findings = _run(model, ctx)
    assert not any("architecture mismatch" in f.issue for f in findings)


def test_non_finite_recorded_loss_yields_finding():
    model = _model(_LOAD_SOURCE)
    ctx = {
        "model": FakeModel({"weight": 0, "bias": 0}),
        "checkpoint": {"weight": 0, "bias": 0, "best_loss": float("nan")},
    }
    findings = _run(model, ctx)
    loss = [f for f in findings if "non-finite" in f.issue]
    assert len(loss) == 1
    assert loss[0].severity == 8


def test_no_checkpoint_signals_yield_no_findings():
    model = _model("model = Net()\n")
    ctx = {"model": FakeModel({"weight": 0, "bias": 0})}
    assert _run(model, ctx) == []


def test_checkpoints_check_is_deterministic():
    model = _model(_LOAD_SOURCE)
    ctx = {
        "model": FakeModel({"weight": 0, "bias": 0}),
        "checkpoint": {"weight": 0, "bias": 0, "extra": 0, "best_loss": float("nan")},
    }
    registry = RuntimeCheckRegistry()
    registry.register(CheckpointsCheck)
    first = [f.to_raw() for f in registry.run_all(model, dict(ctx))]
    second = [f.to_raw() for f in registry.run_all(model, dict(ctx))]
    assert first == second
