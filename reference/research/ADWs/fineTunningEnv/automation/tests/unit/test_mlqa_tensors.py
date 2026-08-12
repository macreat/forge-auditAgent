"""Tests for nb_audit.mlqa.tensors (shape/device/dtype invariants)."""

from __future__ import annotations

import json

from nb_audit.ir import NotebookParser
from nb_audit.mlqa.check_registry import RuntimeCheckRegistry
from nb_audit.mlqa.tensors import TensorCheck


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


def _run(ctx):
    registry = RuntimeCheckRegistry()
    registry.register(TensorCheck)
    return registry.run_all(_model(), ctx)


class FakeTensor:
    """Minimal tensor double exposing shape/dtype/device."""

    def __init__(self, shape, dtype="float32", device="cpu"):
        self.shape = tuple(shape)
        self.dtype = dtype
        self.device = device


def test_batch_size_mismatch_yields_finding():
    ctx = {
        "logits": FakeTensor((10, 3)),
        "labels": FakeTensor((9,)),
    }
    findings = _run(ctx)
    batch = [f for f in findings if "Batch size mismatch" in f.issue]
    assert len(batch) == 1
    assert batch[0].severity == 9


def test_device_mismatch_yields_finding():
    ctx = {
        "logits": FakeTensor((10, 3), device="cuda"),
        "labels": FakeTensor((10,), device="cpu"),
    }
    findings = _run(ctx)
    device = [f for f in findings if "Device mismatch" in f.issue]
    assert len(device) == 1
    assert device[0].severity == 9


def test_int_float_dtype_mismatch_yields_finding():
    ctx = {
        "preds": FakeTensor((10,), dtype="int64"),
        "labels": FakeTensor((10,), dtype="float32"),
    }
    findings = _run(ctx)
    dtype = [f for f in findings if "dtype incompatibility" in f.issue]
    assert len(dtype) == 1
    assert dtype[0].severity == 8


def test_boolean_labels_yield_finding():
    ctx = {
        "preds": FakeTensor((10,), dtype="float32"),
        "labels": FakeTensor((10,), dtype="bool"),
    }
    findings = _run(ctx)
    boolean = [f for f in findings if "Boolean labels" in f.issue]
    assert len(boolean) == 1
    assert boolean[0].severity == 8


def test_matching_tensors_yield_no_finding():
    ctx = {
        "logits": FakeTensor((10, 3)),
        "labels": FakeTensor((10,)),
    }
    findings = _run(ctx)
    assert findings == []


def test_missing_pred_or_label_yields_no_finding():
    ctx = {"logits": FakeTensor((10, 3))}
    assert _run(ctx) == []


def test_tensors_check_is_deterministic():
    ctx = {
        "logits": FakeTensor((10, 3), device="cuda"),
        "labels": FakeTensor((9,), device="cpu", dtype="int64"),
    }
    registry = RuntimeCheckRegistry()
    registry.register(TensorCheck)
    first = [f.to_raw() for f in registry.run_all(_model(), dict(ctx))]
    second = [f.to_raw() for f in registry.run_all(_model(), dict(ctx))]
    assert first == second
