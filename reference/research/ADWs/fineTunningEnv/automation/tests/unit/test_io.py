"""Tests for nb_audit.io — NotebookManager layout, integrity, writes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nb_audit.io import (
    NotebookIntegrityError,
    NotebookManager,
    RunLayout,
    sha256_file,
    utc_timestamp,
)

TINY = (
    '{"cells":[],"metadata":{},'
    '"nbformat":4,"nbformat_minor":5}'
)


def _make_manager(tmp_path: Path, timestamp: str = "20260812T000000000000") -> NotebookManager:
    source = tmp_path / "input.ipynb"
    source.write_text(TINY, encoding="utf-8")
    return NotebookManager(source, base_dir=tmp_path, timestamp=timestamp)


# -- layout ------------------------------------------------------------------ #
def test_setup_creates_required_layout(tmp_path):
    manager = _make_manager(tmp_path)
    layout = manager.setup()

    assert isinstance(layout, RunLayout)
    assert layout.original_path.exists()
    assert layout.final_path.exists()
    assert layout.iterations_dir.is_dir()
    assert layout.audits_dir.is_dir()
    assert layout.artifacts_dir.is_dir()
    assert layout.logs_dir.is_dir()
    assert layout.report_path.exists()
    assert layout.audit_json_path.exists()
    assert layout.run_dir.name == manager.timestamp


def test_run_dir_is_nested_under_audit_runs(tmp_path):
    manager = _make_manager(tmp_path)
    layout = manager.setup()
    assert layout.run_dir == tmp_path / "audit-runs" / manager.timestamp


# -- original preservation + hash ------------------------------------------- #
def test_original_is_copied_byte_identical(tmp_path):
    manager = _make_manager(tmp_path)
    layout = manager.setup()
    assert layout.original_path.read_bytes() == tmp_path.joinpath("input.ipynb").read_bytes()
    assert sha256_file(layout.original_path) == manager.original_hash


def test_final_starts_as_copy_of_original(tmp_path):
    manager = _make_manager(tmp_path)
    layout = manager.setup()
    assert layout.final_path.read_bytes() == layout.original_path.read_bytes()


# -- integrity --------------------------------------------------------------- #
def test_integrity_passes_after_a_run(tmp_path):
    manager = _make_manager(tmp_path)
    manager.setup()
    manager.save_iteration({"cells": [], "nbformat": 4, "nbformat_minor": 5})
    manager.save_audit({"status": "PASS"})
    assert manager.verify_integrity() is True


def test_integrity_fails_closed_when_copy_modified(tmp_path):
    manager = _make_manager(tmp_path)
    layout = manager.setup()
    layout.original_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(NotebookIntegrityError):
        manager.verify_integrity()


def test_integrity_fails_closed_when_source_modified(tmp_path):
    manager = _make_manager(tmp_path)
    manager.setup()
    manager.source_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(NotebookIntegrityError):
        manager.verify_integrity()


# -- writes ------------------------------------------------------------------ #
def test_save_iteration_writes_numbered_files(tmp_path):
    manager = _make_manager(tmp_path)
    manager.setup()
    first = manager.save_iteration({"cells": []})
    second = manager.save_iteration({"cells": []})
    assert first.name == "iteration-001.ipynb"
    assert second.name == "iteration-002.ipynb"
    assert first.exists() and second.exists()


def test_save_final_updates_final_ipynb(tmp_path):
    manager = _make_manager(tmp_path)
    manager.setup()
    patched = '{"cells":[{"cell_type":"code"}],"nbformat":4,"nbformat_minor":5}'
    manager.save_final(patched)
    assert manager.layout.final_path.read_text(encoding="utf-8") == patched


def test_save_audit_writes_parseable_json(tmp_path):
    manager = _make_manager(tmp_path)
    manager.setup()
    manager.save_audit({"status": "PASS", "unresolved_gt8": 0})
    data = json.loads(manager.layout.audit_json_path.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert data["unresolved_gt8"] == 0


def test_save_audit_iteration_writes_to_audits_dir(tmp_path):
    manager = _make_manager(tmp_path)
    manager.setup()
    path = manager.save_audit_iteration({"iteration": 1}, iteration=1)
    assert path.parent.name == "audits"
    assert path.name == "audit-001.json"


def test_save_report_and_log(tmp_path):
    manager = _make_manager(tmp_path)
    manager.setup()
    manager.save_report("# report")
    manager.write_log("run.log", "started")
    assert manager.layout.report_path.read_text(encoding="utf-8") == "# report"
    assert manager.layout.logs_dir.joinpath("run.log").read_text(encoding="utf-8") == "started"


# -- timestamp --------------------------------------------------------------- #
def test_timestamp_is_deterministic_when_injected(tmp_path):
    manager = _make_manager(tmp_path, timestamp="20260812T101010101010")
    assert manager.timestamp == "20260812T101010101010"
    assert manager.run_dir.name == "20260812T101010101010"


def test_utc_timestamp_format():
    ts = utc_timestamp()
    assert len(ts) == len("YYYYMMDDTHHMMSSffffff")
    assert ts[:8].isdigit()
