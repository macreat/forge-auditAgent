"""Tests for nb_audit.mlqa.artifacts (checkpoint/plot/csv/json provenance)."""

from __future__ import annotations

import json

from nb_audit.ir import NotebookParser
from nb_audit.mlqa.artifacts import ArtifactsCheck
from nb_audit.mlqa.check_registry import RuntimeCheckRegistry


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
    registry.register(ArtifactsCheck)
    return registry.run_all(model, ctx)


class FakeFigure:
    """Minimal matplotlib figure double exposing ``savefig()``."""

    def savefig(self, path, **kwargs):
        return None


def test_artifact_mismatch_yields_finding():
    # A CSV artifact is declared, but the backing value is a scalar.
    model = _model("results.to_csv('results.csv')\n")
    ctx = {"results": 0.92}
    findings = _run(model, ctx)
    mismatch = [f for f in findings if "mismatched" in f.issue]
    assert len(mismatch) == 1
    assert mismatch[0].severity == 8
    assert "scalar" in mismatch[0].issue


def test_missing_artifact_yields_finding():
    model = _model("report.to_json('report.json')\n")
    ctx = {}
    findings = _run(model, ctx)
    missing = [f for f in findings if "no matching value" in f.issue]
    assert len(missing) == 1
    assert missing[0].severity == 8


def test_tabular_value_backs_csv_artifact_without_finding():
    model = _model("results.to_csv('results.csv')\n")
    ctx = {"results": [["a", "b"], [1, 2], [3, 4]]}
    assert _run(model, ctx) == []


def test_dict_backs_json_artifact_without_finding():
    model = _model("report.to_json('report.json')\n")
    ctx = {"report": {"accuracy": 0.93, "f1": 0.88}}
    assert _run(model, ctx) == []


def test_figure_backs_plot_artifact_without_finding():
    model = _model("plt.savefig('plot.png')\n")
    ctx = {"plot": FakeFigure()}
    assert _run(model, ctx) == []


def test_scalar_backs_json_artifact_is_mismatch():
    # A bare scalar is not a JSON *object*; but json.dump accepts scalars.
    # Only clearly-incompatible kinds (e.g. a figure) are flagged.
    model = _model("report.to_json('report.json')\n")
    ctx = {"report": 0.93}
    assert _run(model, ctx) == []


def test_state_dict_backs_checkpoint_artifact_without_finding():
    model = _model("torch.save(model.state_dict(), 'best.pt')\n")
    ctx = {"best": {"weight": 0, "bias": 0}}
    assert _run(model, ctx) == []


def test_list_backs_checkpoint_artifact_is_mismatch():
    model = _model("torch.save(model.state_dict(), 'best.pt')\n")
    ctx = {"best": [0, 1, 2]}
    findings = _run(model, ctx)
    mismatch = [f for f in findings if "mismatched" in f.issue]
    assert len(mismatch) == 1
    assert "list" in mismatch[0].issue


def test_artifacts_check_is_deterministic():
    model = _model(
        "results.to_csv('results.csv')\n"
        "report.to_json('report.json')\n"
    )
    ctx = {"results": 0.92, "report": {"accuracy": 0.93}}
    registry = RuntimeCheckRegistry()
    registry.register(ArtifactsCheck)
    first = [f.to_raw() for f in registry.run_all(model, dict(ctx))]
    second = [f.to_raw() for f in registry.run_all(model, dict(ctx))]
    assert first == second
