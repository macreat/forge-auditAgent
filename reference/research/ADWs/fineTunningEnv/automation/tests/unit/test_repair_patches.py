"""Tests for nb_audit.repair.patches — Patch, PatchLog, PatchEngine refusals."""

from __future__ import annotations

import pytest

from nb_audit.ir import CellRef, NotebookModel
from nb_audit.models import Classification, Finding, Location, Status
from nb_audit.repair.patches import (
    PatchEngine,
    PatchLog,
    PatchRefused,
    extract_objective,
    patchable_candidates,
)
from nb_audit.repair.root_cause import RootCause

LEAK_LINE = "X_train, X_test = train_test_split(X, y, test_size=0.2)"
FIXED_LINE = "X_train, X_test = train_test_split(X, y, test_size=0.2, random_state=42)"


def _cell(cell_id, source, cell_type="code", index=0):
    return CellRef(id=cell_id, index=index, cell_type=cell_type, source=source)


def _model(cells, *, objective_markdown=True):
    all_cells = []
    if objective_markdown:
        all_cells.append(
            _cell("md-obj", "# Objective\nClassify digits into 10 classes.\n", "markdown", 0)
        )
    all_cells.extend(cells)
    return NotebookModel(cells=tuple(all_cells))


def _leak_model():
    source = f"{LEAK_LINE}\nmodel.fit(X_train)\nscore = model.score(X_test)\n"
    return _model([_cell("c1", source)])


def _rca(severity=9, category="splits") -> RootCause:
    f = Finding(
        id="F1",
        severity=severity,
        classification=Classification.NEW,
        category=category,
        location=Location(cell="c1", line=1),
        issue="leak",
        root_cause="rc",
        impact="impact",
        correction="correction",
    )
    return RootCause.from_finding(f)


def _engine(objective=None) -> PatchEngine:
    return PatchEngine(objective=objective)


# -- patch attribution + diff ------------------------------------------------ #
def test_patch_carries_finding_id():
    patch = _engine().build_patch("F1", _rca(), _leak_model(), cell_id="c1", line=1, replacement=FIXED_LINE)
    assert patch.finding_id == "F1"
    assert patch.id.startswith("P")


def test_patch_unified_diff_present():
    patch = _engine().build_patch("F1", _rca(), _leak_model(), cell_id="c1", line=1, replacement=FIXED_LINE)
    diff = patch.unified_diff()
    assert "---" in diff
    assert "+++" in diff
    assert f"-{LEAK_LINE}" in diff
    assert f"+{FIXED_LINE}" in diff


def test_patch_log_records_and_diff():
    engine = _engine()
    patch = engine.build_patch("F1", _rca(), _leak_model(), cell_id="c1", line=1, replacement=FIXED_LINE)
    engine.log.add(patch)
    assert len(engine.log) == 1
    assert engine.log.finding_ids() == {"F1"}
    assert "---" in engine.log.unified_diff()


# -- apply ------------------------------------------------------------------- #
def test_apply_produces_new_model_and_preserves_original():
    model = _leak_model()
    engine = _engine()
    patch = engine.build_patch("F1", _rca(), model, cell_id="c1", line=1, replacement=FIXED_LINE)
    new_model = engine.apply(patch, model)

    assert new_model.get_cell("c1").source.startswith(FIXED_LINE)
    assert model.get_cell("c1").source.startswith(LEAK_LINE)  # original untouched
    assert new_model.get_cell("c1").source != model.get_cell("c1").source
    assert len(engine.log) == 1


def test_objective_preserved_after_apply():
    model = _leak_model()
    objective = extract_objective(model)
    engine = _engine(objective=objective)
    patch = engine.build_patch("F1", _rca(), model, cell_id="c1", line=1, replacement=FIXED_LINE)
    new_model = engine.apply(patch, model)
    assert extract_objective(new_model) == objective
    assert "Classify digits into 10 classes" in new_model.get_cell("md-obj").source


# -- refusals ---------------------------------------------------------------- #
def test_engine_refuses_without_rca():
    with pytest.raises(PatchRefused) as exc:
        _engine().build_patch("F1", None, _leak_model(), cell_id="c1", line=1, replacement=FIXED_LINE)
    assert exc.value.reason == "missing_root_cause"


def test_engine_refuses_severity_below_threshold():
    rca = RootCause(
        issue="i", location=Location(cell="c1"), severity=8,
        classification=Classification.NEW, root_cause="r",
        impact="i", correction="c", downstream=(),
    )
    with pytest.raises(PatchRefused) as exc:
        _engine().build_patch("F1", rca, _leak_model(), cell_id="c1", line=1, replacement=FIXED_LINE)
    assert exc.value.reason == "severity_not_patchable"


def test_engine_refuses_missing_finding_id():
    with pytest.raises(PatchRefused) as exc:
        _engine().build_patch("", _rca(), _leak_model(), cell_id="c1", line=1, replacement=FIXED_LINE)
    assert exc.value.reason == "missing_finding_id"


def test_noop_patch_refused_as_fabrication():
    with pytest.raises(PatchRefused) as exc:
        _engine().build_patch("F1", _rca(), _leak_model(), cell_id="c1", line=1, replacement=LEAK_LINE)
    assert exc.value.reason == "noop"


def test_engine_refuses_markdown_cell():
    model = _model([_cell("md-obj", "# Objective\n", "markdown")])
    with pytest.raises(PatchRefused) as exc:
        _engine().build_patch("F1", _rca(), model, cell_id="md-obj", line=1, replacement="x")
    assert exc.value.reason == "not_code_cell"


def test_engine_refuses_unknown_cell_and_line():
    with pytest.raises(PatchRefused) as exc:
        _engine().build_patch("F1", _rca(), _leak_model(), cell_id="nope", line=1, replacement=FIXED_LINE)
    assert exc.value.reason == "unknown_cell"
    with pytest.raises(PatchRefused) as exc:
        _engine().build_patch("F1", _rca(), _leak_model(), cell_id="c1", line=99, replacement=FIXED_LINE)
    assert exc.value.reason == "line_out_of_range"


def test_objective_drift_refused():
    source = "# Objective: classify digits\nmodel.fit(X)\n"
    model = _model([_cell("c1", source)], objective_markdown=False)
    engine = _engine(objective="Objective: classify digits")
    with pytest.raises(PatchRefused) as exc:
        engine.build_patch("F1", _rca(), model, cell_id="c1", line=1, replacement="# removed objective")
    assert exc.value.reason == "objective_drift"


def test_apply_refuses_stale_patch():
    model = _leak_model()
    engine = _engine()
    patch = engine.build_patch("F1", _rca(), model, cell_id="c1", line=1, replacement=FIXED_LINE)
    drifted = NotebookModel(cells=tuple(
        _cell("c1", "something else entirely\n") if c.id == "c1" else c
        for c in model.cells
    ))
    with pytest.raises(PatchRefused) as exc:
        engine.apply(patch, drifted)
    assert exc.value.reason == "stale_patch"


# -- candidate selection ----------------------------------------------------- #
def test_patchable_candidates_is_subset_of_unresolved_gt_8():
    findings = [
        Finding(id="A", severity=9, classification=Classification.NEW, category="splits", location=Location(cell="c1"), issue="x"),
        Finding(id="B", severity=8, classification=Classification.NEW, category="splits", location=Location(cell="c1"), issue="x"),
        Finding(id="C", severity=9, classification=Classification.NEW, category="splits", location=Location(cell="c1"), issue="x", status=Status.RESOLVED),
        Finding(id="D", severity=10, classification=Classification.NEW, category="splits", location=Location(cell="c1"), issue="x"),
    ]
    candidates = patchable_candidates(findings)
    assert {f.id for f in candidates} == {"A", "D"}


def test_patch_line_combined_flow():
    model = _leak_model()
    engine = _engine()
    new_model = engine.patch_line("F1", _rca(), model, cell_id="c1", line=1, replacement=FIXED_LINE)
    assert new_model.get_cell("c1").source.startswith(FIXED_LINE)
    assert len(engine.log) == 1
    assert engine.log.all()[0].finding_id == "F1"
