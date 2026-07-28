"""Pass 1: Structural Overview — section map, red flags, focus areas.

Scans markdown cells for hierarchical headers to build a section map,
identifies immediately visible red flags (missing outputs, broken imports,
orphaned cells), and records user-specified focus areas.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from app.audit.models import Cell, Finding, Notebook, PassResult

_PASS_NAME = "Structural Overview"
_PASS_NUMBER = 1


def run(
    notebook: Notebook,
    focus_areas: list[str] | None = None,
) -> PassResult:
    """Execute Pass 1: Structural Overview.

    Builds a section map from markdown headers, scans for red flags
    (missing outputs, broken imports, orphaned cells), and records
    user-specified focus areas.

    Args:
        notebook: The parsed notebook to analyse.
        focus_areas: Optional list of focus area labels. When provided,
            Pass 1 records them in the deliverable for downstream passes.

    Returns:
        A :class:`PassResult` with status ``"passed"`` if no red flags
        were found, ``"flagged"`` otherwise. Score is ``None`` for this pass.
    """
    findings: list[Finding] = []
    focus = focus_areas or []

    # 1. Section map from markdown headers
    sections = _build_section_map(notebook)

    # 2. Red flags
    findings.extend(_find_missing_outputs(notebook))
    findings.extend(_find_broken_imports(notebook))
    findings.extend(_find_orphaned_cells(notebook))

    # 3. Build deliverable text
    deliverable = _build_deliverable(
        notebook.filename, sections, findings, focus,
    )

    # Status: passed if no red flags (warning/error), flagged otherwise
    red_flag_findings = [
        f for f in findings if f.severity in ("warning", "error")
    ]
    status = "passed" if not red_flag_findings else "flagged"

    return PassResult(
        pass_name=_PASS_NAME,
        pass_number=_PASS_NUMBER,
        score=None,
        status=status,
        findings=findings,
        deliverable_text=deliverable,
    )


# ---------------------------------------------------------------------------
# Section map
# ---------------------------------------------------------------------------


def _build_section_map(notebook: Notebook) -> list[dict[str, Any]]:
    """Scan all markdown cells for ``#`` header syntax.

    Returns:
        Ordered list of dicts with keys ``level``, ``title``,
        ``cell_index``, and ``line_number`` (approximate within the source).
    """
    sections: list[dict[str, Any]] = []
    for cell in notebook.cells:
        if cell.cell_type != "markdown":
            continue
        for line_no, line in enumerate(cell.source.split("\n"), start=1):
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if match:
                sections.append({
                    "level": len(match.group(1)),
                    "title": match.group(2).strip(),
                    "cell_index": cell.index,
                    "line_number": line_no,
                })
    return sections


# ---------------------------------------------------------------------------
# Red flags
# ---------------------------------------------------------------------------


def _find_missing_outputs(notebook: Notebook) -> list[Finding]:
    """Flag code cells marked as executed but with empty output lists.

    A cell whose ``execution_count`` is set (not ``None``) but whose
    ``outputs`` list is empty may indicate the cell produced no visible
    result, which could be intentional (e.g. an assignment) or a sign
    that something is missing.
    """
    findings: list[Finding] = []
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        if cell.execution_count is not None and len(cell.outputs) == 0:
            findings.append(Finding(
                severity="warning",
                cell_index=cell.index,
                category="missing_output",
                message=(
                    f"Cell {cell.index} is marked as executed "
                    f"(execution_count={cell.execution_count}) but has no "
                    f"outputs."
                ),
            ))
    return findings


def _find_broken_imports(notebook: Notebook) -> list[Finding]:
    """Analyse code cells for import-related issues via ``ast`` parsing.

    Detects:
    - Syntax errors in cells that contain import statements.
    - Wildcard imports (``from X import *``), which pollute the namespace.
    """
    findings: list[Finding] = []
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source.strip()
        if not source:
            continue

        # Skip cells without any import statement
        if not re.search(r"^\s*(import |from )", source, re.MULTILINE):
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            findings.append(Finding(
                severity="error",
                cell_index=cell.index,
                category="broken_import",
                message=(
                    f"Cell {cell.index}: syntax error parsing code — "
                    f"{exc.msg} (line {exc.lineno})"
                ),
            ))
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                wild = [n for n in node.names if n.name == "*"]
                if wild:
                    module = node.module or ""
                    findings.append(Finding(
                        severity="warning",
                        cell_index=cell.index,
                        category="broken_import",
                        message=(
                            f"Cell {cell.index}: wildcard import "
                            f"'from {module} import *' — can cause "
                            f"namespace pollution and name masking."
                        ),
                    ))

    return findings


def _find_orphaned_cells(notebook: Notebook) -> list[Finding]:
    """Identify code cells whose defined names are never used downstream.

    For each code cell, extracts defined names (assignments, function
    definitions, class definitions, imported names) using AST. If
    *none* of those names appear in any later cell, the cell is flagged
    as orphaned.
    """
    findings: list[Finding] = []

    # Collect definitions per cell (only code cells with runnable source)
    cell_defs: dict[int, set[str]] = {}
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source.strip()
        if not source:
            cell_defs[cell.index] = set()
            continue
        try:
            tree = ast.parse(source)
            cell_defs[cell.index] = _extract_defined_names(tree)
        except SyntaxError:
            cell_defs[cell.index] = set()

    sorted_indices = sorted(cell_defs.keys())
    for i, idx in enumerate(sorted_indices):
        defs = cell_defs[idx]
        if not defs:
            continue

        referenced = False
        for jdx in sorted_indices[i + 1:]:
            later_source = notebook.cells[jdx].source
            for name in defs:
                if name in later_source:
                    referenced = True
                    break
            if referenced:
                break

        if not referenced:
            names_str = ", ".join(sorted(defs)[:5])
            extra = f" and {len(defs) - 5} more" if len(defs) > 5 else ""
            findings.append(Finding(
                severity="info",
                cell_index=idx,
                category="orphaned_cell",
                message=(
                    f"Cell {idx}: defines ({names_str}){extra} but none "
                    f"are referenced by later cells."
                ),
            ))

    return findings


def _extract_defined_names(tree: ast.AST) -> set[str]:
    """Return the set of names *defined* in an AST.

    Covers:
    - Direct assignments (``x = ...``)
    - Function and class definitions
    - ``import X`` and ``from X import Y`` statements
    """
    names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _collect_name_nodes(target, names)
        elif isinstance(node, ast.AnnAssign) and node.target is not None:
            _collect_name_nodes(node.target, names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name.split(".")[0])

    return names


def _collect_name_nodes(node: ast.AST, target: set[str]) -> None:
    """Walk a nested assignment target and collect ``ast.Name`` ids."""
    if isinstance(node, ast.Name):
        target.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            _collect_name_nodes(elt, target)
    elif isinstance(node, ast.Starred):
        _collect_name_nodes(node.value, target)
    elif isinstance(node, ast.Attribute):
        # e.g. ``obj.attr = value`` — we consider ``obj`` as "used"
        pass


# ---------------------------------------------------------------------------
# Deliverable text
# ---------------------------------------------------------------------------


def _build_deliverable(
    filename: str,
    sections: list[dict[str, Any]],
    findings: list[Finding],
    focus_areas: list[str],
) -> str:
    """Build the narrative report text for PDF export."""
    lines: list[str] = [
        f"# Pass 1: Structural Overview — {filename}",
        "",
    ]

    # Focus areas
    if focus_areas:
        lines.append(f"**Focus areas**: {', '.join(focus_areas)}")
        lines.append("")

    # Section map
    lines.append("## Section Map")
    lines.append("")
    if not sections:
        lines.append("No clear section headers detected in markdown cells.")
    else:
        lines.append(f"Found {len(sections)} header(s):")
        lines.append("")
        for sec in sections:
            indent = "  " * (sec["level"] - 1)
            lines.append(
                f"  {indent}- Cell #{sec['cell_index']}: "
                f"{'#' * sec['level']} {sec['title']}"
            )
    lines.append("")

    # Red flags
    lines.append("## Red Flags")
    lines.append("")
    if not findings:
        lines.append("None identified — notebook structure looks clean.")
    else:
        by_severity: dict[str, list[Finding]] = {}
        for f in findings:
            by_severity.setdefault(f.severity, []).append(f)
        for sev in ("error", "warning", "info"):
            items = by_severity.get(sev, [])
            if not items:
                continue
            label = sev.upper()
            lines.append(f"### {label}")
            for f in items:
                cell_ref = f"Cell {f.cell_index}" if f.cell_index is not None else "Notebook"
                lines.append(f"  - [{cell_ref}] [{f.category}] {f.message}")
            lines.append("")

    return "\n".join(lines).strip()
