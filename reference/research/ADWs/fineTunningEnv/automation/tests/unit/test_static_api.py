"""Tests for nb_audit.static.api_checks (torch/sklearn/torchvision misuse)."""

from __future__ import annotations

import json
from pathlib import Path

from nb_audit.ir import NotebookModel, NotebookParser
from nb_audit.static.api_checks import ApiChecksCheck
from nb_audit.static.check_registry import CheckRegistry

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _parse(name: str) -> NotebookModel:
    return NotebookParser().parse_file(str(FIXTURES / name))


def _parse_raw(source: str) -> NotebookModel:
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


def _run(model: NotebookModel):
    registry = CheckRegistry()
    registry.register(ApiChecksCheck)
    return registry.run(model)


# --------------------------------------------------------------------------- #
# missing zero_grad
# --------------------------------------------------------------------------- #
def test_api_misuse_fixture_yields_zero_grad_finding():
    findings = _run(_parse("api_misuse.ipynb"))
    zero_grad = [f for f in findings if "zero_grad" in f.issue]
    assert len(zero_grad) == 1
    assert zero_grad[0].severity == 8
    assert zero_grad[0].category == "api_misuse"


def test_zero_grad_present_suppresses_finding():
    model = _parse_raw(
        "import torch\n"
        "import torch.nn as nn\n"
        "model = nn.Linear(10, 2)\n"
        "optimizer = torch.optim.SGD(model.parameters(), lr=0.01)\n"
        "optimizer.zero_grad()\n"
        "loss = model(x).sum()\n"
        "loss.backward()\n"
        "optimizer.step()\n"
    )
    findings = _run(model)
    assert not any("zero_grad" in f.issue for f in findings)


def test_scheduler_only_step_is_not_flagged():
    model = _parse_raw(
        "scheduler.step()\n"
    )
    findings = _run(model)
    assert not any("zero_grad" in f.issue for f in findings)


# --------------------------------------------------------------------------- #
# train/eval mode
# --------------------------------------------------------------------------- #
def test_eval_without_model_eval_yields_finding():
    model = _parse_raw(
        "from sklearn.metrics import accuracy_score\n"
        "model.train()\n"
        "acc = accuracy_score(y_true, y_pred)\n"
    )
    findings = _run(model)
    mode = [f for f in findings if "model.eval()" in f.issue]
    assert len(mode) == 1
    assert mode[0].severity == 7


def test_model_eval_present_suppresses_mode_finding():
    model = _parse_raw(
        "from sklearn.metrics import accuracy_score\n"
        "model.train()\n"
        "model.eval()\n"
        "acc = accuracy_score(y_true, y_pred)\n"
    )
    findings = _run(model)
    assert not any("model.eval()" in f.issue for f in findings)


# --------------------------------------------------------------------------- #
# softmax + CrossEntropyLoss
# --------------------------------------------------------------------------- #
def test_softmax_with_cross_entropy_yields_finding():
    model = _parse_raw(
        "import torch.nn as nn\n"
        "import torch.nn.functional as F\n"
        "logits = F.softmax(model(x), dim=1)\n"
        "loss = nn.CrossEntropyLoss()(logits, y)\n"
    )
    findings = _run(model)
    ce = [f for f in findings if "CrossEntropyLoss" in f.issue]
    assert len(ce) == 1
    assert ce[0].severity == 8


def test_no_softmax_no_cross_entropy_finding():
    model = _parse_raw(
        "import torch.nn as nn\n"
        "loss = nn.CrossEntropyLoss()(logits, y)\n"
    )
    findings = _run(model)
    assert not any("CrossEntropyLoss" in f.issue for f in findings)


# --------------------------------------------------------------------------- #
# determinism (T-14 AC)
# --------------------------------------------------------------------------- #
def test_api_checks_is_deterministic():
    model = _parse("api_misuse.ipynb")
    registry = CheckRegistry()
    registry.register(ApiChecksCheck)
    first = [f.to_raw() for f in registry.run(model)]
    second = [f.to_raw() for f in registry.run(model)]
    assert first == second
