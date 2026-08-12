"""Tests for nb_audit.mlqa.metrics (range / zero-division / averaging)."""

from __future__ import annotations

import json

from nb_audit.ir import NotebookParser
from nb_audit.mlqa.check_registry import RuntimeCheckRegistry
from nb_audit.mlqa.metrics import MetricCheck


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
    registry.register(MetricCheck)
    return registry.run_all(_model(), ctx)


def test_out_of_range_accuracy_yields_finding():
    findings = _run({"accuracy": 1.5})
    assert len(findings) == 1
    assert findings[0].severity == 8
    assert "range [0, 1]" in findings[0].issue


def test_negative_precision_yields_finding():
    findings = _run({"precision": -0.2})
    assert len(findings) == 1
    assert "outside the valid" in findings[0].issue


def test_nan_metric_yields_zero_division_finding():
    findings = _run({"f1": float("nan")})
    assert len(findings) == 1
    assert findings[0].severity == 8
    assert "NaN" in findings[0].issue


def test_infinite_metric_yields_finding():
    findings = _run({"recall": float("inf")})
    assert len(findings) == 1
    assert "infinite" in findings[0].issue


def test_per_class_array_yields_averaging_finding():
    findings = _run({"precision": [0.9, 0.8]})
    assert len(findings) == 1
    assert findings[0].severity == 7
    assert "averaging" in findings[0].issue


def test_valid_metric_yields_no_finding():
    assert _run({"accuracy": 0.93, "f1": 0.88, "roc_auc": 0.91}) == []


def test_non_metric_names_are_ignored():
    assert _run({"epoch": 100, "lr": 0.001, "loss": 0.25}) == []


def test_metrics_check_is_deterministic():
    ctx = {"accuracy": 1.5, "precision": [0.9, 0.8], "recall": float("nan")}
    registry = RuntimeCheckRegistry()
    registry.register(MetricCheck)
    first = [f.to_raw() for f in registry.run_all(_model(), dict(ctx))]
    second = [f.to_raw() for f in registry.run_all(_model(), dict(ctx))]
    assert first == second
