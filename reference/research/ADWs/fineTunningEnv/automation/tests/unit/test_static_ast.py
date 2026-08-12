"""Tests for nb_audit.static.ast_analysis (undefined names, order, seeds, splits)."""

from __future__ import annotations

from pathlib import Path

from nb_audit.ir import NotebookModel, NotebookParser
from nb_audit.static.ast_analysis import AstAnalysisCheck
from nb_audit.static.check_registry import CheckRegistry

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _parse(name: str) -> NotebookModel:
    return NotebookParser().parse_file(str(FIXTURES / name))


def _parse_raw(source: str) -> NotebookModel:
    return _parse_cells([source])


def _parse_cells(sources: list[str]) -> NotebookModel:
    import json

    cells = [
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "id": f"c{i}",
            "source": src,
        }
        for i, src in enumerate(sources)
    ]
    raw = json.dumps({
        "cells": cells,
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    })
    return NotebookParser().parse(raw)


def _run(model: NotebookModel):
    registry = CheckRegistry()
    registry.register(AstAnalysisCheck)
    return registry.run(model)


def _categories(findings) -> set[str]:
    return {f.category for f in findings}


# --------------------------------------------------------------------------- #
# undefined names (T-12)
# --------------------------------------------------------------------------- #
def test_undefined_name_fixture_yields_finding():
    findings = _run(_parse("undefined_var.ipynb"))
    undefined = [f for f in findings if f.category == "undefined_name"]
    assert len(undefined) == 1
    assert "not_defined_anywhere" in undefined[0].issue
    assert undefined[0].severity == 9


def test_defined_and_imported_names_are_not_flagged():
    findings = _run(_parse("tiny.ipynb"))
    assert _categories(findings) - {"splits", "reproducibility", "execution_order"} == set()
    assert not any(f.category == "undefined_name" for f in findings)


def test_use_before_definition_is_flagged_as_execution_order():
    model = _parse_cells(
        [
            "print(features)\n",
            "def load_data():\n"
            "    return [1, 2, 3]\n"
            "features = load_data()\n",
        ]
    )
    findings = _run(model)
    order = [f for f in findings if f.category == "execution_order"]
    assert len(order) == 1
    assert "features" in order[0].issue
    assert order[0].severity == 8


# --------------------------------------------------------------------------- #
# missing seed (T-12)
# --------------------------------------------------------------------------- #
def test_missing_seed_fixture_yields_reproducibility_finding():
    findings = _run(_parse("missing_seed.ipynb"))
    seeds = [f for f in findings if f.category == "reproducibility"]
    assert len(seeds) == 1
    assert seeds[0].severity == 8
    assert "seed" in seeds[0].issue.lower()


def test_seeded_notebook_has_no_reproducibility_finding():
    model = _parse_raw(
        "import torch\n"
        "torch.manual_seed(42)\n"
        "x = torch.randn(10)\n"
    )
    findings = _run(model)
    assert not any(f.category == "reproducibility" for f in findings)


def test_random_state_on_split_satisfies_seed_requirement():
    model = _parse_raw(
        "from sklearn.model_selection import train_test_split\n"
        "X_train, X_test = train_test_split(X, y, random_state=42)\n"
    )
    findings = _run(model)
    assert not any(f.category == "reproducibility" for f in findings)


# --------------------------------------------------------------------------- #
# split definitions (T-12)
# --------------------------------------------------------------------------- #
def test_training_without_split_yields_splits_finding():
    model = _parse_raw(
        "from sklearn.linear_model import LogisticRegression\n"
        "model = LogisticRegression()\n"
        "model.fit(X, y)\n"
    )
    findings = _run(model)
    splits = [f for f in findings if f.category == "splits"]
    assert any("no train/test/validation split" in f.issue for f in splits)


def test_split_defined_suppresses_missing_split_finding():
    model = _parse_raw(
        "from sklearn.model_selection import train_test_split\n"
        "from sklearn.linear_model import LogisticRegression\n"
        "X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=0)\n"
        "model = LogisticRegression().fit(X_train, y_train)\n"
    )
    findings = _run(model)
    assert not any(
        f.category == "splits" and "no train/test/validation split" in f.issue
        for f in findings
    )


def test_unseeded_split_yields_splits_finding():
    model = _parse_raw(
        "from sklearn.model_selection import train_test_split\n"
        "X_train, X_test = train_test_split(X, y)\n"
    )
    findings = _run(model)
    assert any(
        f.category == "splits" and "without random_state" in f.issue for f in findings
    )


# --------------------------------------------------------------------------- #
# determinism (T-14 AC)
# --------------------------------------------------------------------------- #
def test_ast_analysis_is_deterministic():
    model = _parse("missing_seed.ipynb")
    registry = CheckRegistry()
    registry.register(AstAnalysisCheck)
    first = [f.to_raw() for f in registry.run(model)]
    second = [f.to_raw() for f in registry.run(model)]
    assert first == second
