"""Tests for nb_audit.repair.propagation — PropagationGraph over the IR chain."""

from __future__ import annotations

from nb_audit.repair.propagation import PropagationGraph, PropagationResult
from nb_audit.repair.root_cause import IR_CHAIN


def test_graph_chain_matches_spec():
    assert PropagationGraph().chain == IR_CHAIN


def test_downstream_of_data_is_full_chain():
    graph = PropagationGraph()
    assert graph.downstream("data") == IR_CHAIN[1:]


def test_downstream_of_last_section_is_empty():
    graph = PropagationGraph()
    assert graph.downstream("qa") == ()


def test_leakage_patch_reflags_metrics_plots_conclusions():
    graph = PropagationGraph()
    result = graph.reflag("F1", "leakage")
    assert isinstance(result, PropagationResult)
    assert result.finding_id == "F1"
    assert result.source_section == "data"
    assert {"metrics", "plots", "conclusions"} <= set(result.downstream)


def test_splits_patch_reflags_downstream_too():
    graph = PropagationGraph()
    down = set(graph.affected("splits"))
    assert {"train", "val", "test", "metrics", "plots", "conclusions", "qa"} <= down


def test_metrics_finding_reflags_plots_conclusions_qa():
    graph = PropagationGraph()
    down = set(graph.affected("metrics"))
    assert {"plots", "conclusions", "qa"} <= down
    assert "metrics" not in down  # propagation is strictly downstream


def test_propagation_marks_but_does_not_fabricate_code():
    graph = PropagationGraph()
    result = graph.reflag("F1", "splits")
    # only section names, never code / cell mutations
    assert all(isinstance(s, str) for s in result.downstream)
    assert not hasattr(result, "code")
    assert not hasattr(result, "cells")
    assert result.downstream == graph.downstream("data")
