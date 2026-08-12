"""Tests for nb_audit.ir — NotebookModel, CellRef, NotebookParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from nb_audit.ir import (
    NotebookModel,
    NotebookParseError,
    NotebookParser,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _fixture_text(name: str = "tiny.ipynb") -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parse(raw: str) -> NotebookModel:
    return NotebookParser().parse(raw)


# -- cells ------------------------------------------------------------------- #
def test_parser_populates_cells_from_fixture():
    model = _parse(_fixture_text())
    assert len(model.cells) == 3
    assert model.cells[0].cell_type == "markdown"
    assert model.cells[0].index == 0
    assert model.cells[0].id == "md-intro"
    assert model.cells[1].cell_type == "code"
    assert model.cells[2].cell_type == "code"


def test_cell_source_is_joined_and_ast_attached():
    model = _parse(_fixture_text())
    code = [c for c in model.cells if c.cell_type == "code"]
    assert code[0].source.startswith("import numpy as np")
    assert code[0].ast is not None  # code cells carry an AST
    markdown = model.cells[0]
    assert markdown.ast is None  # non-code cells carry no AST


def test_exec_count_is_normalized():
    model = _parse(_fixture_text())
    code = model.code_cells
    assert code[0].exec_count == 1
    assert code[1].exec_count == 2
    assert model.cells[0].exec_count is None  # markdown has no execution_count


# -- semantic sections ------------------------------------------------------- #
def test_parser_populates_imports():
    model = _parse(_fixture_text())
    names = {imp.name for imp in model.imports}
    assert "numpy" in names
    assert "sklearn.model_selection.train_test_split" in names
    np_import = next(i for i in model.imports if i.name == "numpy")
    assert np_import.alias == "np"


def test_parser_populates_variables():
    model = _parse(_fixture_text())
    names = [v.name for v in model.variables]
    assert "X" in names
    assert "y" in names


def test_fixture_has_no_functions_datasets_or_models():
    model = _parse(_fixture_text())
    assert model.functions == ()
    assert model.datasets == ()
    assert model.models == ()


def test_semantic_sections_detected_from_richer_notebook():
    raw = (
        '{"cells":[{"cell_type":"code","execution_count":null,'
        '"metadata":{},"outputs":[],"id":"c1","source":['
        '"import pandas as pd\\n",'
        '"from sklearn.model_selection import train_test_split\\n",'
        '"from sklearn.metrics import accuracy_score\\n",'
        '"import torch, torch.nn as nn, torch.optim as optim\\n",'
        '"df = pd.read_csv(\\"train.csv\\")\\n",'
        '"X_train, X_test = train_test_split(df, test_size=0.2)\\n",'
        '"model = nn.Sequential(nn.Linear(10, 1))\\n",'
        '"opt = optim.Adam(model.parameters())\\n",'
        '"acc = accuracy_score(y_true, y_pred)\\n",'
        '"torch.save(model.state_dict(), \\"model.pt\\")\\n"'
        ']}],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    model = _parse(raw)

    assert [d.name for d in model.datasets] == ["pd.read_csv"]
    assert [s.name for s in model.splits] == ["train_test_split"]
    assert any(m.name == "nn.Sequential" for m in model.models)
    assert any(o.name == "optim.Adam" for o in model.optimizers)
    assert [m.name for m in model.metrics] == ["accuracy_score"]
    artifacts = [a for a in model.artifacts]
    assert any(a.name == "torch.save" for a in artifacts)
    torch_save = next(a for a in artifacts if a.name == "torch.save")
    assert torch_save.path == "model.pt"


def test_configuration_and_variants_captured():
    raw = (
        '{"cells":[{"cell_type":"code","execution_count":null,'
        '"metadata":{},"outputs":[],"id":"c1","source":['
        '"config = {\\"lr\\": 0.001, \\"epochs\\": 10}\\n",'
        '"variants = [{\\"lr\\": 0.001}, {\\"lr\\": 0.01}]\\n"'
        ']}],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    model = _parse(raw)
    assert model.configuration["config"] == {"lr": 0.001, "epochs": 10}
    assert len(model.experiment_variants) == 1
    assert model.experiment_variants[0].name == "variants"


# -- immutability ------------------------------------------------------------ #
def test_notebook_model_is_frozen():
    model = _parse(_fixture_text())
    with pytest.raises(Exception):
        model.cells = ()  # type: ignore[misc]
    with pytest.raises(Exception):
        model.configuration = {}  # type: ignore[misc]


# -- error handling ---------------------------------------------------------- #
def test_invalid_json_raises_notebook_parse_error():
    with pytest.raises(NotebookParseError):
        _parse("{ this is not json }")


def test_valid_json_but_not_a_notebook_raises():
    with pytest.raises(NotebookParseError):
        _parse("[1, 2, 3]")
    with pytest.raises(NotebookParseError):
        _parse('{"foo": "bar"}')


def test_syntax_error_cell_does_not_raise():
    raw = (
        '{"cells":[{"cell_type":"code","execution_count":null,'
        '"metadata":{},"outputs":[],"id":"c1","source":["def broken( :\\n"]}],'
        '"metadata":{},"nbformat":4,"nbformat_minor":5}'
    )
    model = _parse(raw)
    assert len(model.cells) == 1
    assert model.cells[0].ast is None  # syntax error -> no AST, not a crash


def test_parse_file_reads_from_path():
    model = NotebookParser().parse_file(str(FIXTURES / "tiny.ipynb"))
    assert len(model.cells) == 3


def test_parse_file_missing_path_raises(tmp_path):
    with pytest.raises(NotebookParseError):
        NotebookParser().parse_file(str(tmp_path / "missing.ipynb"))
