"""Syntax check: compile each code cell, report invalid Python as severity-10.

Notebook JSON validity is handled upstream by :class:`~nb_audit.ir.NotebookParser`
(which raises :class:`~nb_audit.ir.NotebookParseError` on invalid notebooks and
sets ``CellRef.ast = None`` on per-cell syntax errors). This check re-compiles
each code cell's source to recover the precise error message and line number, and
emits a deterministic severity-10 finding. It is fully LLM-free.
"""

from __future__ import annotations

from nb_audit.ir import NotebookModel
from nb_audit.models import Finding, Location
from nb_audit.static.check_registry import StaticCheck


class SyntaxCheck(StaticCheck):
    """Reports code cells whose Python source does not compile."""

    name = "syntax"
    category = "syntax"
    severity = 10

    def check(self, model: NotebookModel) -> list[Finding]:
        findings: list[Finding] = []
        for cell in model.cells:
            if cell.cell_type != "code":
                continue
            error = _syntax_error(cell.source)
            if error is None:
                continue
            line, message = error
            findings.append(
                self.finding(
                    location=Location(cell=cell.id, line=line),
                    issue=f"Syntax error: {message}",
                    root_cause="Invalid Python syntax prevents this cell from executing",
                    impact="Notebook cannot execute until the syntax is fixed",
                    correction="Repair the cell source so it compiles cleanly",
                )
            )
        return findings


def _syntax_error(source: str) -> tuple[int | None, str] | None:
    """Return ``(line, message)`` if ``source`` fails to compile, else ``None``.

    ``compile()`` raises :class:`SyntaxError` for most invalid source and
    :class:`ValueError` for a few edge cases (e.g. embedded null bytes). Both
    are treated as syntax-level problems here.
    """
    try:
        compile(source, "<notebook-cell>", "exec")
    except SyntaxError as exc:
        line = getattr(exc, "lineno", None)
        return line, (exc.msg or str(exc))
    except ValueError as exc:
        return None, str(exc)
    return None
