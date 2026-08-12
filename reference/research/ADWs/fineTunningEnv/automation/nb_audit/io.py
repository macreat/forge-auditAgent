"""Notebook run management: immutable original, audit-run layout, integrity.

:class:`NotebookManager` copies the original notebook into a timestamped
``audit-runs/<timestamp>/`` run directory, lays out the structure required by
REQ-002, records a sha256 of the original, and provides fail-closed integrity
verification so the original can never be silently mutated during a run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from nb_audit.config import AuditConfig


class NotebookIntegrityError(Exception):
    """Raised when the original notebook changed during a run (fail closed)."""


def sha256_file(path: Path) -> str:
    """Return the lowercase hex sha256 digest of ``path``."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_timestamp() -> str:
    """Deterministic, sortable UTC timestamp: ``YYYYMMDDTHHMMSSffffff``."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


@dataclass(frozen=True)
class RunLayout:
    """Filesystem paths for one audit run (REQ-002 / spec §10, §26)."""

    run_dir: Path
    original_path: Path
    final_path: Path
    iterations_dir: Path
    audits_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    report_path: Path
    audit_json_path: Path


class NotebookManager:
    """Owns an audit run: copies the original, creates the run layout, and
    verifies integrity fail-closed."""

    def __init__(
        self,
        notebook_path: str | Path,
        base_dir: str | Path | None = None,
        config: AuditConfig | None = None,
        timestamp: str | None = None,
    ) -> None:
        self.config = config or AuditConfig()
        self.source_path = Path(notebook_path).resolve()
        if not self.source_path.exists():
            raise FileNotFoundError(f"Notebook not found: {self.source_path}")
        self.base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
        self.timestamp = timestamp or utc_timestamp()
        self._original_bytes = self.source_path.read_bytes()
        self.original_hash = sha256_file(self.source_path)
        self._layout: RunLayout | None = None
        self._iteration_count = 0

    # -- layout ------------------------------------------------------------ #
    @property
    def run_dir(self) -> Path:
        return self.layout.run_dir

    @property
    def layout(self) -> RunLayout:
        if self._layout is None:
            self._layout = self.setup()
        return self._layout

    def setup(self) -> RunLayout:
        """Create the run directory and its required layout (idempotent)."""
        run_dir = self.base_dir / "audit-runs" / self.timestamp
        layout = RunLayout(
            run_dir=run_dir,
            original_path=run_dir / "original.ipynb",
            final_path=run_dir / "final.ipynb",
            iterations_dir=run_dir / "iterations",
            audits_dir=run_dir / "audits",
            artifacts_dir=run_dir / "artifacts",
            logs_dir=run_dir / "logs",
            report_path=run_dir / "report.md",
            audit_json_path=run_dir / "audit.json",
        )
        for directory in (
            layout.iterations_dir,
            layout.audits_dir,
            layout.artifacts_dir,
            layout.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not layout.original_path.exists():
            layout.original_path.write_bytes(self._original_bytes)
        if not layout.final_path.exists():
            layout.final_path.write_bytes(self._original_bytes)
        if not layout.report_path.exists():
            layout.report_path.write_text("", encoding="utf-8")
        if not layout.audit_json_path.exists():
            layout.audit_json_path.write_text("{}\n", encoding="utf-8")
        return layout

    def __enter__(self) -> "NotebookManager":
        self.setup()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    # -- integrity --------------------------------------------------------- #
    def verify_integrity(self) -> bool:
        """Fail closed: raise if the original changed during the run.

        Checks (a) that our managed ``original.ipynb`` copy is byte-identical to
        the hash captured at start, and (b) — when ``preserve_original`` is on —
        that the source file still matches too.
        """
        layout = self.layout
        if sha256_file(layout.original_path) != self.original_hash:
            raise NotebookIntegrityError(
                "original.ipynb was modified during the run"
            )
        if self.config.audit.preserve_original and self.source_path.exists():
            if sha256_file(self.source_path) != self.original_hash:
                raise NotebookIntegrityError(
                    "source notebook changed during the run"
                )
        return True

    # -- writes ------------------------------------------------------------ #
    def save_iteration(self, notebook: Any, iteration: int | None = None) -> Path:
        """Write an iteration copy to ``iterations/iteration-NNN.ipynb``."""
        layout = self.layout
        index = iteration if iteration is not None else self._next_iteration()
        path = layout.iterations_dir / f"iteration-{index:03d}.ipynb"
        self._write_notebook(path, notebook)
        self._iteration_count = max(self._iteration_count, index)
        return path

    def save_final(self, notebook: Any) -> Path:
        """Write the final (post-patch) notebook to ``final.ipynb``."""
        layout = self.layout
        self._write_notebook(layout.final_path, notebook)
        return layout.final_path

    def save_audit(self, data: Mapping[str, Any]) -> Path:
        """Write the canonical audit document to ``audit.json``."""
        path = self.layout.audit_json_path
        path.write_text(self._json_text(data), encoding="utf-8")
        return path

    def save_audit_iteration(self, data: Mapping[str, Any], iteration: int | None = None) -> Path:
        """Write one iteration's audit to ``audits/audit-NNN.json``."""
        index = iteration if iteration is not None else max(self._iteration_count, 1)
        path = self.layout.audits_dir / f"audit-{index:03d}.json"
        path.write_text(self._json_text(data), encoding="utf-8")
        return path

    def save_report(self, text: str) -> Path:
        """Write the markdown report to ``report.md``."""
        path = self.layout.report_path
        path.write_text(text, encoding="utf-8")
        return path

    def write_log(self, name: str, text: str) -> Path:
        """Append/write a log entry under ``logs/``."""
        path = self.layout.logs_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    # -- internals --------------------------------------------------------- #
    def _next_iteration(self) -> int:
        self._iteration_count += 1
        return self._iteration_count

    @staticmethod
    def _json_text(data: Mapping[str, Any]) -> str:
        return json.dumps(dict(data), indent=2) + "\n"

    @staticmethod
    def _write_notebook(path: Path, notebook: Any) -> None:
        if isinstance(notebook, str):
            text = notebook
        elif isinstance(notebook, bytes):
            text = notebook.decode("utf-8")
        elif isinstance(notebook, Mapping):
            text = json.dumps(dict(notebook), indent=2)
        else:
            raise TypeError(
                f"Unsupported notebook type: {type(notebook).__name__!r}"
            )
        path.write_text(text, encoding="utf-8")
