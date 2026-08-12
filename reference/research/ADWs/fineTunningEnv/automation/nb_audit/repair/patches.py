"""Minimal, attributed, line-level patches (spec §16, §27).

The patch engine transforms notebook cell source one line at a time, producing
minimal unified diffs recorded in a :class:`PatchLog`. Every patch carries the
``finding_id`` it addresses so it can be traced back to a finding.

Safety constraints (spec §16, §27) — the engine REFUSES (raises
:class:`PatchRefused`) instead of silently misbehaving:

- no :class:`~nb_audit.repair.root_cause.RootCause` → ``missing_root_cause``;
- ``rca.severity <= 8`` → ``severity_not_patchable`` (never auto-lower severity);
- a replacement that equals the original line → ``noop`` (never fabricate a
  no-change patch);
- a replacement that removes the research objective → ``objective_drift``
  (never drift the notebook objective);
- target cell missing / not a code cell / line out of range / stale source.

The objective is either supplied to the engine or extracted from the notebook's
first non-empty markdown cell (``extract_objective``). Patches never target
markdown cells, so the objective is preserved by construction and checked again
as a guard.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, replace
from typing import Iterable

from nb_audit.ir import CellRef, NotebookModel
from nb_audit.models import Status
from nb_audit.repair.root_cause import RootCause


# --------------------------------------------------------------------------- #
# Objective extraction
# --------------------------------------------------------------------------- #
def extract_objective(model: NotebookModel) -> str:
    """Return the research objective: the first non-empty markdown cell source."""
    for cell in model.cells:
        if cell.cell_type == "markdown" and cell.source.strip():
            return cell.source.strip()
    return ""


# --------------------------------------------------------------------------- #
# Patch
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Patch:
    """One minimal, line-level cell-source transform attributed to a finding."""

    id: str
    finding_id: str
    cell_id: str
    line: int  # 1-indexed line number within the cell source
    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]
    kind: str = "line_replace"

    @property
    def before(self) -> str:
        return "".join(self.old_lines)

    @property
    def after(self) -> str:
        return "".join(self.new_lines)

    def unified_diff(self) -> str:
        """Return this patch as a unified diff (old → new line)."""
        return _unified_diff(
            self.before,
            self.after,
            fromfile=f"a/{self.cell_id}:{self.line}",
            tofile=f"b/{self.cell_id}:{self.line}",
        )


def _unified_diff(old_text: str, new_text: str, fromfile: str, tofile: str) -> str:
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )


# --------------------------------------------------------------------------- #
# PatchLog
# --------------------------------------------------------------------------- #
class PatchLog:
    """Insertion-ordered record of applied patches with a unified-diff log."""

    def __init__(self) -> None:
        self._patches: list[Patch] = []

    def add(self, patch: Patch) -> None:
        self._patches.append(patch)

    def all(self) -> list[Patch]:
        return list(self._patches)

    def finding_ids(self) -> set[str]:
        return {p.finding_id for p in self._patches}

    def unified_diff(self) -> str:
        return "\n".join(p.unified_diff() for p in self._patches)

    def __iter__(self):
        return iter(self._patches)

    def __len__(self) -> int:
        return len(self._patches)


# --------------------------------------------------------------------------- #
# PatchRefused
# --------------------------------------------------------------------------- #
class PatchRefused(Exception):
    """Raised when the patch engine refuses to act (safety constraint)."""

    def __init__(self, reason: str, finding_id: str = "", detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.finding_id = finding_id


# --------------------------------------------------------------------------- #
# PatchEngine
# --------------------------------------------------------------------------- #
class PatchEngine:
    """Builds and applies minimal, attributed, diffable line-level patches."""

    PATCH_THRESHOLD = 8  # only severity > 8 is patchable (spec §7)

    def __init__(self, objective: str | None = None) -> None:
        self.objective = objective
        self.log = PatchLog()
        self._next_id = 0

    # -- patchability ------------------------------------------------------ #
    @classmethod
    def is_patchable(cls, finding) -> bool:
        """True when a finding is an unresolved severity>8 patch candidate."""
        return (
            finding.severity > cls.PATCH_THRESHOLD
            and finding.status is Status.UNRESOLVED
        )

    # -- objective --------------------------------------------------------- #
    def _resolved_objective(self, model: NotebookModel) -> str:
        if self.objective is not None:
            return self.objective
        return extract_objective(model)

    # -- build ------------------------------------------------------------- #
    def build_patch(
        self,
        finding_id: str,
        rca: RootCause | None,
        model: NotebookModel,
        *,
        cell_id: str,
        line: int,
        replacement: str,
    ) -> Patch:
        """Validate a single-line transform and return an attributed :class:`Patch`.

        Raises :class:`PatchRefused` on any safety-constraint violation.
        """
        if rca is None:
            raise PatchRefused(
                "missing_root_cause", finding_id,
                "a RootCause is required before patching a severity>8 finding",
            )
        if rca.severity <= self.PATCH_THRESHOLD:
            raise PatchRefused(
                "severity_not_patchable", finding_id,
                f"severity {rca.severity} is not patchable (> {self.PATCH_THRESHOLD})",
            )
        if not finding_id:
            raise PatchRefused("missing_finding_id", finding_id)

        cell = model.get_cell(cell_id)
        if cell is None:
            raise PatchRefused("unknown_cell", finding_id, f"cell {cell_id!r} not found")
        if cell.cell_type != "code":
            raise PatchRefused(
                "not_code_cell", finding_id,
                f"cell {cell_id!r} is not a code cell",
            )

        lines = cell.source.splitlines(keepends=True)
        if line < 1 or line > len(lines):
            raise PatchRefused(
                "line_out_of_range", finding_id,
                f"line {line} out of range for cell {cell_id!r}",
            )

        old_line = lines[line - 1]
        new_line = _normalize_line(replacement, old_line)

        if new_line == old_line:
            raise PatchRefused(
                "noop", finding_id,
                "refusing to fabricate a patch that does not change the source",
            )

        objective = self._resolved_objective(model)
        if objective and objective in old_line and objective not in new_line:
            raise PatchRefused(
                "objective_drift", finding_id,
                "patch would remove the research objective",
            )

        self._next_id += 1
        return Patch(
            id=f"P{self._next_id:04d}",
            finding_id=finding_id,
            cell_id=cell_id,
            line=line,
            old_lines=(old_line,),
            new_lines=(new_line,),
        )

    # -- apply ------------------------------------------------------------- #
    def apply(self, patch: Patch, model: NotebookModel) -> NotebookModel:
        """Apply a pre-built patch, log it, and return a NEW notebook model.

        The original ``model`` is never mutated (frozen dataclass). The patched
        cell keeps its id/index/type/execution-count but gets the new source and
        a cleared AST (semantic sections are re-derived on the next parse).
        """
        cell = model.get_cell(patch.cell_id)
        if cell is None:
            raise PatchRefused("unknown_cell", patch.finding_id)
        lines = cell.source.splitlines(keepends=True)
        if patch.line < 1 or patch.line > len(lines):
            raise PatchRefused("line_out_of_range", patch.finding_id)
        if lines[patch.line - 1] != patch.old_lines[0]:
            raise PatchRefused(
                "stale_patch", patch.finding_id,
                "cell source changed since the patch was built",
            )

        new_source = "".join(
            lines[: patch.line - 1] + list(patch.new_lines) + lines[patch.line:]
        )
        new_cells = tuple(
            CellRef(
                id=c.id,
                index=c.index,
                cell_type=c.cell_type,
                source=new_source,
                exec_count=c.exec_count,
                metadata=c.metadata,
                ast=None,
            )
            if c.id == patch.cell_id
            else c
            for c in model.cells
        )
        self.log.add(patch)
        return replace(model, cells=new_cells)

    # -- combined ---------------------------------------------------------- #
    def patch_line(
        self,
        finding_id: str,
        rca: RootCause | None,
        model: NotebookModel,
        *,
        cell_id: str,
        line: int,
        replacement: str,
    ) -> NotebookModel:
        """Build and apply a single-line patch in one step."""
        patch = self.build_patch(
            finding_id, rca, model,
            cell_id=cell_id, line=line, replacement=replacement,
        )
        return self.apply(patch, model)


def _normalize_line(replacement: str, old_line: str) -> str:
    """Match the replacement's trailing newline to the original line's."""
    if old_line.endswith("\n"):
        return replacement if replacement.endswith("\n") else replacement + "\n"
    return replacement[:-1] if replacement.endswith("\n") else replacement


# --------------------------------------------------------------------------- #
# Candidate selection helper
# --------------------------------------------------------------------------- #
def patchable_candidates(findings: Iterable) -> list:
    """Return unresolved severity>8 findings (the only valid patch candidates)."""
    return [f for f in findings if PatchEngine.is_patchable(f)]
