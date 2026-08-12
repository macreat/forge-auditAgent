"""Tests for nb_audit.config — resolution chain and defaults."""

from __future__ import annotations

import os

import pytest

from nb_audit.config import AuditConfig


def test_defaults_when_nothing_provided():
    cfg = AuditConfig()
    assert cfg.audit.severity_threshold == 8
    assert cfg.audit.max_iterations == 10
    assert cfg.audit.execute_notebook is True
    assert cfg.audit.preserve_original is True
    assert cfg.llm.temperature == 0.0
    assert cfg.llm.max_retries == 2
    assert cfg.execution.timeout_seconds == 3600
    assert cfg.execution.allow_network is False
    assert cfg.execution.kernel_name == "python3"
    assert cfg.qa.require_clean_execution is True
    assert cfg.qa.require_artifacts is True
    assert cfg.qa.require_reproducibility_checks is True


def test_missing_yaml_file_resolves_to_defaults(tmp_path):
    cfg = AuditConfig.from_yaml(tmp_path / "nope.yaml")
    assert cfg.audit.severity_threshold == 8
    assert cfg.audit.max_iterations == 10


def test_yaml_overrides_defaults(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "audit:\n  severity_threshold: 9\n  max_iterations: 3\n"
        "execution:\n  timeout_seconds: 60\n  allow_network: true\n"
    )
    cfg = AuditConfig.from_yaml(path)
    assert cfg.audit.severity_threshold == 9
    assert cfg.audit.max_iterations == 3
    assert cfg.execution.timeout_seconds == 60
    assert cfg.execution.allow_network is True
    # untouched fields keep defaults
    assert cfg.audit.execute_notebook is True
    assert cfg.qa.require_artifacts is True


def test_env_overrides_yaml(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("audit:\n  max_iterations: 3\n")
    monkeypatch.setenv("NB_AUDIT_MAX_ITERATIONS", "7")
    monkeypatch.setenv("NB_AUDIT_LLM_BASE_URL", "http://localhost:1234/v1")
    cfg = AuditConfig.load(yaml_path=path)
    assert cfg.audit.max_iterations == 7  # env beats yaml
    assert cfg.llm.base_url == "http://localhost:1234/v1"


def test_cli_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NB_AUDIT_SEVERITY_THRESHOLD", "9")
    cfg = AuditConfig.load(cli={"audit": {"severity_threshold": 6}})
    assert cfg.audit.severity_threshold == 6  # cli beats env


def test_env_bool_and_int_coercion(monkeypatch):
    monkeypatch.setenv("NB_AUDIT_EXECUTION_ALLOW_NETWORK", "true")
    monkeypatch.setenv("NB_AUDIT_EXECUTION_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("NB_AUDIT_EXECUTE_NOTEBOOK", "0")
    cfg = AuditConfig.from_env()
    assert cfg.execution.allow_network is True
    assert cfg.execution.timeout_seconds == 120
    assert cfg.audit.execute_notebook is False


def test_env_var_names_cover_documented_set(monkeypatch):
    monkeypatch.setenv("NB_AUDIT_MAX_ITERATIONS", "5")
    monkeypatch.setenv("NB_AUDIT_SEVERITY_THRESHOLD", "7")
    monkeypatch.setenv("NB_AUDIT_LLM_BASE_URL", "http://x")
    monkeypatch.setenv("NB_AUDIT_LLM_MODEL", "test-model")
    monkeypatch.setenv("NB_AUDIT_EXECUTION_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("NB_AUDIT_EXECUTION_ALLOW_NETWORK", "1")
    cfg = AuditConfig.from_env()
    assert cfg.audit.max_iterations == 5
    assert cfg.audit.severity_threshold == 7
    assert cfg.llm.base_url == "http://x"
    assert cfg.llm.model == "test-model"
    assert cfg.execution.timeout_seconds == 99
    assert cfg.execution.allow_network is True


def test_invalid_bool_env_raises(monkeypatch):
    monkeypatch.setenv("NB_AUDIT_EXECUTION_ALLOW_NETWORK", "maybe")
    with pytest.raises(ValueError):
        AuditConfig.from_env()


def test_load_without_any_input_uses_defaults(monkeypatch):
    for name in list(os.environ):
        if name.startswith("NB_AUDIT_"):
            monkeypatch.delenv(name)
    cfg = AuditConfig.load()
    assert cfg.audit.severity_threshold == 8
    assert cfg.execution.kernel_name == "python3"
