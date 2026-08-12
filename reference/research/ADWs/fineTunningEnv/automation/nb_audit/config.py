"""Configuration for the nb-audit pipeline.

Resolution order (highest precedence last)::

    defaults < config.yaml < env (NB_AUDIT_*) < cli flags

No pydantic — plain dataclasses with ``from_raw`` / ``from_yaml`` / ``from_env``
classmethods. A missing config file resolves to the documented defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Any, Callable, Mapping

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a runtime dependency
    yaml = None


# --------------------------------------------------------------------------- #
# Coercion helpers (env vars and YAML both arrive as strings)
# --------------------------------------------------------------------------- #
def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    return int(value)


def _coerce_float(value: Any) -> float:
    return float(value)


def _coerce_str(value: Any) -> str:
    return str(value)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n", ""}:
        return False
    raise ValueError(f"cannot coerce {value!r} to bool")


# --------------------------------------------------------------------------- #
# Section dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class AuditSection:
    severity_threshold: int = 8
    max_iterations: int = 10
    execute_notebook: bool = True
    preserve_original: bool = True


@dataclass
class LLMSection:
    model: str = ""
    base_url: str = ""
    temperature: float = 0.0
    max_retries: int = 2


@dataclass
class ExecutionSection:
    timeout_seconds: int = 3600
    allow_network: bool = False
    kernel_name: str = "python3"


@dataclass
class QASection:
    require_clean_execution: bool = True
    require_artifacts: bool = True
    require_reproducibility_checks: bool = True


# Field coercer table keyed by (section, field). Drives both YAML and env parsing.
_COERCERS: dict[tuple[str, str], Callable[[Any], Any]] = {
    ("audit", "severity_threshold"): _coerce_int,
    ("audit", "max_iterations"): _coerce_int,
    ("audit", "execute_notebook"): _coerce_bool,
    ("audit", "preserve_original"): _coerce_bool,
    ("llm", "model"): _coerce_str,
    ("llm", "base_url"): _coerce_str,
    ("llm", "temperature"): _coerce_float,
    ("llm", "max_retries"): _coerce_int,
    ("execution", "timeout_seconds"): _coerce_int,
    ("execution", "allow_network"): _coerce_bool,
    ("execution", "kernel_name"): _coerce_str,
    ("qa", "require_clean_execution"): _coerce_bool,
    ("qa", "require_artifacts"): _coerce_bool,
    ("qa", "require_reproducibility_checks"): _coerce_bool,
}

# env var -> (section, field)
_ENV_VARS: dict[str, tuple[str, str]] = {
    "NB_AUDIT_SEVERITY_THRESHOLD": ("audit", "severity_threshold"),
    "NB_AUDIT_MAX_ITERATIONS": ("audit", "max_iterations"),
    "NB_AUDIT_EXECUTE_NOTEBOOK": ("audit", "execute_notebook"),
    "NB_AUDIT_PRESERVE_ORIGINAL": ("audit", "preserve_original"),
    "NB_AUDIT_LLM_MODEL": ("llm", "model"),
    "NB_AUDIT_LLM_BASE_URL": ("llm", "base_url"),
    "NB_AUDIT_LLM_TEMPERATURE": ("llm", "temperature"),
    "NB_AUDIT_LLM_MAX_RETRIES": ("llm", "max_retries"),
    "NB_AUDIT_EXECUTION_TIMEOUT_SECONDS": ("execution", "timeout_seconds"),
    "NB_AUDIT_EXECUTION_ALLOW_NETWORK": ("execution", "allow_network"),
    "NB_AUDIT_EXECUTION_KERNEL_NAME": ("execution", "kernel_name"),
    "NB_AUDIT_QA_REQUIRE_CLEAN_EXECUTION": ("qa", "require_clean_execution"),
    "NB_AUDIT_QA_REQUIRE_ARTIFACTS": ("qa", "require_artifacts"),
    "NB_AUDIT_QA_REQUIRE_REPRODUCIBILITY_CHECKS": ("qa", "require_reproducibility_checks"),
}

_SECTIONS: dict[str, type] = {
    "audit": AuditSection,
    "llm": LLMSection,
    "execution": ExecutionSection,
    "qa": QASection,
}


def _build_section(section_name: str, raw: Mapping[str, Any] | None) -> Any:
    """Build one section dataclass from a raw (possibly string-typed) mapping."""
    section_cls = _SECTIONS[section_name]
    kwargs: dict[str, Any] = {}
    for f in fields(section_cls):
        coercer = _COERCERS[(section_name, f.name)]
        value = raw.get(f.name) if raw else None
        kwargs[f.name] = f.default if value is None else coercer(value)
    return section_cls(**kwargs)


def _deep_merge(base: dict, override: Mapping[str, Any]) -> dict:
    """Recursively merge ``override`` onto ``base``; override wins per key."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _env_to_raw(environ: Mapping[str, str]) -> dict:
    """Convert NB_AUDIT_* env vars into a nested section mapping."""
    raw: dict[str, dict] = {}
    for env_name, (section, name) in _ENV_VARS.items():
        if env_name not in environ or environ[env_name] == "":
            continue
        coercer = _COERCERS[(section, name)]
        raw.setdefault(section, {})[name] = coercer(environ[env_name])
    return raw


@dataclass
class AuditConfig:
    """Root configuration, mirroring the audit/ llm/ execution/ qa/ sections."""

    audit: AuditSection = field(default_factory=AuditSection)
    llm: LLMSection = field(default_factory=LLMSection)
    execution: ExecutionSection = field(default_factory=ExecutionSection)
    qa: QASection = field(default_factory=QASection)

    # -- constructors ------------------------------------------------------ #
    @classmethod
    def from_raw(cls, raw: Mapping[str, Any] | None) -> "AuditConfig":
        raw = raw or {}
        return cls(
            audit=_build_section("audit", raw.get("audit")),
            llm=_build_section("llm", raw.get("llm")),
            execution=_build_section("execution", raw.get("execution")),
            qa=_build_section("qa", raw.get("qa")),
        )

    @classmethod
    def from_yaml(cls, path: os.PathLike[str] | str) -> "AuditConfig":
        path = os.fspath(path)
        if not os.path.exists(path):
            return cls()
        if yaml is None:
            raise ImportError("PyYAML is required to load a config file")
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return cls.from_raw(data if isinstance(data, dict) else {})

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AuditConfig":
        environ = os.environ if environ is None else environ
        return cls.from_raw(_env_to_raw(environ))

    @classmethod
    def from_cli(cls, cli: Mapping[str, Any] | None) -> "AuditConfig":
        return cls.from_raw(cli or {})

    @classmethod
    def load(
        cls,
        yaml_path: os.PathLike[str] | str | None = None,
        cli: Mapping[str, Any] | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> "AuditConfig":
        """Resolve the full precedence chain: defaults < yaml < env < cli."""
        environ = os.environ if environ is None else environ
        raw: dict[str, Any] = {}
        if yaml_path and os.path.exists(os.fspath(yaml_path)):
            raw = cls.from_yaml(yaml_path).as_raw()
        raw = _deep_merge(raw, _env_to_raw(environ))
        if cli:
            raw = _deep_merge(raw, dict(cli))
        return cls.from_raw(raw)

    # -- serialization ----------------------------------------------------- #
    def as_raw(self) -> dict:
        """Return a nested dict of section fields (useful for merging/layers)."""
        return {
            "audit": {f.name: getattr(self.audit, f.name) for f in fields(AuditSection)},
            "llm": {f.name: getattr(self.llm, f.name) for f in fields(LLMSection)},
            "execution": {f.name: getattr(self.execution, f.name) for f in fields(ExecutionSection)},
            "qa": {f.name: getattr(self.qa, f.name) for f in fields(QASection)},
        }
