"""Unit tests for nb_audit.execute — kernel-independent logic.

The kernel-dependent paths (real ipykernel execution, timeout killing a
``while True`` cell) are exercised by the integration suite; these tests cover
the pure pieces: status semantics, namespace serialization, capture-cell source
generation, error-output scanning, and the severity-10 execution finding.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import numpy as np

from nb_audit.config import AuditConfig
from nb_audit.execute import (
    ERROR,
    KILLED,
    SUCCESS,
    TIMEOUT,
    ExecutionResult,
    NotebookExecutor,
    _as_notebook_node,
    _capture_cell_source,
    _find_error_cells,
    _load_namespace,
    build_execution_finding,
    is_capturable,
    serialize_namespace,
)


def _nb_with_cells(cells):
    return {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


# -- status semantics -------------------------------------------------------- #
def test_execution_result_ok_only_for_success():
    assert ExecutionResult(SUCCESS).ok is True
    assert ExecutionResult(ERROR).ok is False
    assert ExecutionResult(TIMEOUT).ok is False
    assert ExecutionResult(KILLED).ok is False


def test_execution_result_default_namespace_is_empty():
    result = ExecutionResult(SUCCESS)
    assert result.namespace == {}


# -- namespace serialization ------------------------------------------------ #
# A stand-in for a class defined inside a notebook's kernel namespace, whose
# ``__module__`` is ``"__main__"`` (unpicklable by reference from the parent).
class _LocalClass:
    pass


_LocalClass.__module__ = "__main__"


def test_is_capturable_filters_modules_callables_classes_and_main_types():
    assert is_capturable(types) is False
    assert is_capturable(lambda: None) is False
    assert is_capturable(_LocalClass) is False
    assert is_capturable(_LocalClass()) is False  # __main__-defined type
    assert is_capturable(open) is False
    assert is_capturable([1, 2, 3]) is True
    assert is_capturable({"a": 1}) is True
    assert is_capturable(3.14) is True


def test_is_capturable_keeps_numpy_arrays_and_skips_open_handles(tmp_path):
    assert is_capturable(np.arange(5)) is True
    with open(tmp_path / "f.txt", "w") as fh:
        assert is_capturable(fh) is False


def test_serialize_namespace_filters_underscore_and_uncapturable():
    namespace = {
        "_hidden": 1,
        "np": np,
        "keep": [1, 2, 3],
        "arr": np.arange(3),
        "local": _LocalClass(),
        "func": lambda: 1,
    }
    result = serialize_namespace(namespace)
    assert set(result) == {"keep", "arr"}
    assert result["keep"] == [1, 2, 3]


# -- capture cell source ----------------------------------------------------- #
def test_capture_cell_source_embeds_path_and_pickle():
    source = _capture_cell_source("/tmp/run/.nb_audit_namespace.pkl")
    assert "/tmp/run/.nb_audit_namespace.pkl" in source
    assert "pickle" in source
    assert "_nb_audit_out" in source


# -- namespace load ---------------------------------------------------------- #
def test_load_namespace_round_trips_serializable_values(tmp_path):
    import pickle

    path = tmp_path / "ns.pkl"
    with open(path, "wb") as fh:
        pickle.dump({"a": 1, "b": [1, 2]}, fh, protocol=4)
    assert _load_namespace(path) == {"a": 1, "b": [1, 2]}


def test_load_namespace_returns_empty_on_missing_file(tmp_path):
    assert _load_namespace(tmp_path / "missing.pkl") == {}


def test_load_namespace_returns_empty_on_corrupt_file(tmp_path):
    path = tmp_path / "bad.pkl"
    path.write_bytes(b"not a pickle")
    assert _load_namespace(path) == {}


# -- notebook normalization -------------------------------------------------- #
def test_as_notebook_node_from_dict_is_a_fresh_copy():
    raw = _nb_with_cells([])
    node = _as_notebook_node(raw)
    node.cells.append({"cell_type": "code", "source": "x = 1", "metadata": {}})
    assert len(raw["cells"]) == 0  # original untouched


def test_as_notebook_node_from_path(tmp_path):
    path = tmp_path / "nb.ipynb"
    path.write_text(json.dumps(_nb_with_cells([])), encoding="utf-8")
    node = _as_notebook_node(str(path))
    assert node.nbformat == 4


# -- error output scanning --------------------------------------------------- #
def test_find_error_cells_detects_error_outputs():
    nb = _nb_with_cells([
        {"cell_type": "code", "id": "ok", "outputs": [], "metadata": {}, "source": "x = 1"},
        {
            "cell_type": "code",
            "id": "bad",
            "metadata": {},
            "source": "1/0",
            "outputs": [
                {
                    "output_type": "error",
                    "ename": "ZeroDivisionError",
                    "evalue": "division by zero",
                }
            ],
        },
    ])
    errors = _find_error_cells(nb)
    assert len(errors) == 1
    index, ename, evalue = errors[0]
    assert index == 1
    assert ename == "ZeroDivisionError"
    assert "division by zero" in evalue


def test_find_error_cells_returns_empty_when_clean():
    nb = _nb_with_cells([
        {"cell_type": "code", "id": "ok", "outputs": [], "metadata": {}, "source": "x = 1"}
    ])
    assert _find_error_cells(nb) == []


# -- execution finding ------------------------------------------------------- #
def test_build_execution_finding_is_severity_10_execution():
    nb = _nb_with_cells([{"cell_type": "code", "id": "cell-3", "outputs": [], "metadata": {}, "source": "1/0"}])
    finding = build_execution_finding(nb, 0, "ZeroDivisionError", "division by zero", ERROR)
    assert finding.severity == 10
    assert finding.category == "execution"
    assert finding.location.cell == "cell-3"
    assert "failed" in finding.issue


def test_build_execution_finding_timeout_variant():
    finding = build_execution_finding(None, None, "", "Cell execution timed out", TIMEOUT)
    assert finding.severity == 10
    assert finding.category == "execution"
    assert "timed out" in finding.issue
    assert finding.location.cell == ""


# -- kernel env -------------------------------------------------------------- #
def test_kernel_env_denies_network_by_default():
    executor = NotebookExecutor(config=AuditConfig())
    env = executor.kernel_env()
    assert env["IPY_ALLOW_NETWORK"] == "0"
    assert env["NB_AUDIT_ALLOW_NETWORK"] == "0"


def test_kernel_env_allows_network_when_enabled():
    config = AuditConfig()
    config.execution.allow_network = True
    executor = NotebookExecutor(config=config)
    assert executor.kernel_env() == {}


def test_kernel_env_explicit_override():
    config = AuditConfig()
    config.execution.allow_network = True
    executor = NotebookExecutor(config=config)
    assert executor.kernel_env(allow_network=False)["IPY_ALLOW_NETWORK"] == "0"
    assert executor.kernel_env(allow_network=True) == {}


# -- timeout resolution ------------------------------------------------------ #
def test_executor_uses_config_timeout_default():
    config = AuditConfig()
    assert config.execution.timeout_seconds == 3600
    assert config.execution.kernel_name == "python3"
