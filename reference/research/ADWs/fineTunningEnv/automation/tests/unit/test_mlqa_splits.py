"""Tests for nb_audit.mlqa.splits (split disjointness + reproducibility)."""

from __future__ import annotations

import json

from nb_audit.ir import NotebookParser
from nb_audit.mlqa.check_registry import RuntimeCheckRegistry
from nb_audit.mlqa.splits import SplitCheck


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


def _run(model, ctx):
    registry = RuntimeCheckRegistry()
    registry.register(SplitCheck)
    return registry.run_all(model, ctx)


class FakeSubset:
    """Minimal torch.utils.data.Subset double exposing ``.indices``."""

    def __init__(self, indices):
        self.indices = list(indices)


def test_train_test_overlap_yields_leakage_finding():
    model = _model("")
    ctx = {"train_ids": [0, 1, 2], "val_ids": [1, 2, 3]}
    findings = _run(model, ctx)
    leakage = [f for f in findings if f.category == "splits"]
    assert len(leakage) == 1
    assert leakage[0].severity == 9
    assert "TRAIN ∩ VALIDATION" in leakage[0].issue


def test_disjoint_splits_yield_no_finding():
    model = _model("")
    ctx = {"train_ids": [0, 1, 2], "val_ids": [3, 4, 5], "test_ids": [6, 7]}
    findings = _run(model, ctx)
    assert not any(f.category == "splits" for f in findings)


def test_overlapping_subset_indices_yield_leakage_finding():
    model = _model("")
    ctx = {
        "train_set": FakeSubset([0, 1, 2, 3]),
        "val_set": FakeSubset([3, 4, 5]),
    }
    findings = _run(model, ctx)
    leakage = [f for f in findings if f.category == "splits"]
    assert len(leakage) == 1
    assert "overlap of 1" in leakage[0].issue


def test_raw_label_arrays_are_not_flagged_as_overlap():
    # 1-D label arrays naturally share values; only id-like names are compared.
    model = _model("")
    ctx = {"y_train": [0, 1, 0], "y_test": [0, 1, 1]}
    findings = _run(model, ctx)
    assert not any(f.category == "splits" for f in findings)


def test_randomized_split_without_seed_yields_reproducibility_finding():
    model = _model("train_test_split(data)\n")
    ctx = {"train_ids": [0, 1, 2], "val_ids": [3, 4, 5]}
    findings = _run(model, ctx)
    repro = [f for f in findings if f.category == "reproducibility"]
    assert len(repro) == 1
    assert repro[0].severity == 8
    assert "seed" in repro[0].issue.lower()


def test_seed_in_namespace_suppresses_reproducibility_finding():
    model = _model("train_test_split(data)\n")
    ctx = {"train_ids": [0, 1, 2], "val_ids": [3, 4, 5], "seed": 42}
    findings = _run(model, ctx)
    assert not any(f.category == "reproducibility" for f in findings)


def test_splits_check_is_deterministic():
    model = _model("train_test_split(data)\n")
    ctx = {"train_ids": [0, 1, 2], "val_ids": [1, 2, 3]}
    registry = RuntimeCheckRegistry()
    registry.register(SplitCheck)
    first = [f.to_raw() for f in registry.run_all(model, dict(ctx))]
    second = [f.to_raw() for f in registry.run_all(model, dict(ctx))]
    assert first == second
