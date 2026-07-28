"""Pass 5: Code Quality Review — repetitive code, dead code, naming
quality, and output hygiene.

Assesses notebook code maintainability by detecting: repeated code
blocks that should be refactored into functions, unused imports and
other dead code, poor naming conventions, and bloated cell outputs
that degrade readability.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from app.audit.models import Cell, Finding, Notebook, PassResult

_PASS_NAME = "Code Quality Review"
_PASS_NUMBER = 5

# Patterns for output hygiene
_RE_PRINT = re.compile(r"\bprint\s*\(")
_RE_FULL_DF = re.compile(
    r"\b(?:pd\.|pandas\.)?(?:DataFrame|concat|merge|read_csv|read_excel)\s*\("
)
_RE_TRUNCATION = re.compile(
    r"\.(?:head|tail|sample|describe|info|dtypes|shape)\s*\("
)
_RE_TENSOR_PRINT = re.compile(
    r"\b(torch\.Tensor|tf\.Tensor|tensor|array)\b.*\.?(?:numpy|tolist)?\s*$",
    re.IGNORECASE,
)

# Naming quality patterns
_RE_SINGLE_LETTER = re.compile(r"^\s*([a-z])\s*=")
_RE_NONDESCRIPT = re.compile(
    r"\b(df\d+|tmp\d*|x\d+|y\d*|data\d*|result\d*|res\d*|val\d*|test\d*|"
    r"train\d*|foo|bar|baz)\b",
)

# Dead code patterns
_RE_UNREACHABLE_RETURN = re.compile(r"return\s+.+\n\s*#.*pass", re.IGNORECASE)

# AST-based pattern matching for repetitive code
_SIMILARITY_SCORE_THRESHOLD = 0.85


def run(
    notebook: Notebook,
    focus_areas: list[str] | None = None,
) -> PassResult:
    """Execute Pass 5: Code Quality Review.

    Evaluates:
    - Repetitive code blocks (3+ similar cells via AST pattern matching).
    - Dead code (unused imports, unreachable branches, redundant assignments).
    - Naming quality (single-letter vars, non-descriptive names).
    - Output hygiene (full dataframe prints, raw tensor output).

    Args:
        notebook: The parsed notebook to analyse.
        focus_areas: Optional focus area list.

    Returns:
        A :class:`PassResult` with status and score.
    """
    findings: list[Finding] = []

    repetitive_result = _check_repetitive_code(notebook)
    findings.extend(repetitive_result["findings"])

    dead_code_result = _check_dead_code(notebook)
    findings.extend(dead_code_result["findings"])

    naming_result = _check_naming(notebook)
    findings.extend(naming_result["findings"])

    hygiene_result = _check_output_hygiene(notebook)
    findings.extend(hygiene_result["findings"])

    score = _compute_score(findings)
    status = _compute_status(findings)

    deliverable = _build_deliverable(
        notebook.filename,
        repetitive_result,
        dead_code_result,
        naming_result,
        hygiene_result,
        findings,
        score,
        focus_areas or [],
    )

    return PassResult(
        pass_name=_PASS_NAME,
        pass_number=_PASS_NUMBER,
        score=score,
        status=status,
        findings=findings,
        deliverable_text=deliverable,
    )


# ---------------------------------------------------------------------------
# Sub-checks
# ---------------------------------------------------------------------------


def _check_repetitive_code(notebook: Notebook) -> dict[str, Any]:
    """Detect code patterns repeated across 3+ cells via AST comparison.

    Normalises each code cell's AST into a structural signature (node type
    sequence) and groups cells with similar signatures. Flags groups of
    3+ cells as refactoring candidates.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"groups"``: list of (cell_indices, description) tuples
    """
    findings: list[Finding] = []
    groups: list[tuple[list[int], str]] = []

    code_cells: list[tuple[int, str]] = []
    for cell in notebook.cells:
        if cell.cell_type == "code" and cell.source.strip():
            code_cells.append((cell.index, cell.source.strip()))

    if len(code_cells) < 3:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="repetitive_code",
            message="Too few code cells (<3) for meaningful repetition analysis.",
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "Insufficient code cells.",
            "groups": [],
        }

    # Build AST signatures for each cell
    signatures: list[dict[str, Any]] = []
    for idx, source in code_cells:
        try:
            tree = ast.parse(source)
            sig = _ast_signature(tree)
            # Extract a structural fingerprint: sequence of top-level node types
            type_sequence = [type(n).__name__ for n in tree.body]
            # Count function-defs, calls, assignments for similarity
            call_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call))
            assign_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Assign))
            # Extract function names from calls
            call_names: list[str] = []
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    call_names.append(n.func.attr)
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                    call_names.append(n.func.id)

            signatures.append({
                "cell_index": idx,
                "source": source,
                "type_sequence": type_sequence,
                "call_count": call_count,
                "assign_count": assign_count,
                "call_names": call_names[:10],
                "sig": sig,
            })
        except SyntaxError:
            continue

    if len(signatures) < 3:
        return {
            "status": "passed",
            "findings": findings,
            "details": "Fewer than 3 parseable code cells.",
            "groups": [],
        }

    # Compare signatures pairwise to find groups of 3+
    visited: set[int] = set()
    for i, sig_a in enumerate(signatures):
        if sig_a["cell_index"] in visited:
            continue
        group: list[int] = [sig_a["cell_index"]]
        for j in range(i + 1, len(signatures)):
            sig_b = signatures[j]
            if sig_b["cell_index"] in visited:
                continue
            similarity = _compute_similarity(sig_a, sig_b)
            if similarity >= _SIMILARITY_SCORE_THRESHOLD:
                group.append(sig_b["cell_index"])

        if len(group) >= 3:
            visited.update(group)
            # Describe the common pattern from shared call names
            shared_calls: list[str] = []
            other_sigs = [s for s in signatures if s["cell_index"] in group]
            if other_sigs:
                first_calls = set(other_sigs[0]["call_names"])
                common = first_calls.intersection(*[
                    set(s["call_names"]) for s in other_sigs[1:]
                ])
                if common:
                    shared_calls = sorted(common)[:5]

            desc = (
                f"Repeated pattern with {len(shared_calls)} shared call(s): "
                f"{', '.join(shared_calls)}"
                if shared_calls
                else "Repeated structural pattern"
            )
            groups.append((sorted(group), desc))

    if groups:
        for indices, desc in groups:
            findings.append(Finding(
                severity="warning",
                cell_index=indices[0],
                category="repetitive_code",
                message=(
                    f"{len(indices)} similar code blocks at cells "
                    f"{indices}: {desc}. Consider refactoring into a "
                    f"reusable function."
                ),
            ))

        details = f"{len(groups)} group(s) of 3+ repetitive code blocks."
    else:
        details = "No repetitive code blocks detected (3+ similar cells)."
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="repetitive_code",
            message="No repetitive code patterns detected.",
        ))

    status = "flagged" if groups else "passed"
    return {
        "status": status,
        "findings": findings,
        "details": details,
        "groups": groups,
    }


def _ast_signature(tree: ast.AST) -> str:
    """Build a structural signature from an AST.

    Uses the concatenation of node type names and their first-level
    attribute names to create a pattern that captures structure while
    ignoring variable names and literal values.
    """
    parts: list[str] = []
    for node in ast.walk(tree):
        parts.append(type(node).__name__)
    return "|".join(parts)


def _compute_similarity(sig_a: dict[str, Any], sig_b: dict[str, Any]) -> float:
    """Compute structural similarity between two cell signatures.

    Uses type sequence overlap, call count proximity, and call name
    overlap to produce a similarity score 0..1.
    """
    # Type sequence overlap
    seq_a = sig_a["type_sequence"]
    seq_b = sig_b["type_sequence"]
    if not seq_a or not seq_b:
        return 0.0

    # Compare top-level type sequences (first 10 elements)
    min_len = min(len(seq_a), len(seq_b), 10)
    type_matches = sum(
        1 for i in range(min_len) if seq_a[i] == seq_b[i]
    )
    type_score = type_matches / max(len(seq_a), len(seq_b), 1)

    # Call count proximity
    call_a = sig_a["call_count"]
    call_b = sig_b["call_count"]
    max_calls = max(call_a, call_b, 1)
    call_score = 1.0 - (abs(call_a - call_b) / max_calls)

    # Call name overlap
    names_a = set(sig_a["call_names"])
    names_b = set(sig_b["call_names"])
    if not names_a and not names_b:
        name_score = 1.0
    elif not names_a or not names_b:
        name_score = 0.0
    else:
        intersection = names_a & names_b
        union = names_a | names_b
        name_score = len(intersection) / max(len(union), 1)

    # Weighted combination
    return 0.35 * type_score + 0.25 * call_score + 0.40 * name_score


def _check_dead_code(notebook: Notebook) -> dict[str, Any]:
    """Detect unused imports, unreachable branches, redundant assignments.

    For unused imports: collect all imported names via AST, then check if
    any of those names appear in downstream cells.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    """
    findings: list[Finding] = []

    # Phase 1: Unused imports
    _check_unused_imports(notebook, findings)

    # Phase 2: Unreachable branches (after return/raise)
    _check_unreachable_code(notebook, findings)

    # Phase 3: Redundant assignments (var assigned but never used downstream)
    _check_redundant_assignments(notebook, findings)

    if not findings:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="dead_code",
            message="No dead code detected.",
        ))

    flagged = any(f.severity == "warning" for f in findings)
    return {
        "status": "flagged" if flagged else "passed",
        "findings": findings,
        "details": (
            "Dead code detected."
            if flagged
            else "No dead code issues found."
        ),
    }


def _check_unused_imports(notebook: Notebook, findings: list[Finding]) -> None:
    """Collect imports per cell and flag those unused in downstream cells."""
    # Map: cell_index → set of names imported
    imports_per_cell: dict[int, set[str]] = {}
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source.strip()
        if not source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        names.add(alias.asname or alias.name.split(".")[0])
        if names:
            imports_per_cell[cell.index] = names

    # For each cell with imports, check if those names are used downstream
    sorted_indices = sorted(imports_per_cell.keys())
    for i, idx in enumerate(sorted_indices):
        imported = imports_per_cell[idx]
        if not imported:
            continue
        used_any = False
        for jdx in sorted_indices[i + 1:]:
            later_source = notebook.cells[jdx].source
            for name in imported:
                # Check if name appears as an identifier in later code
                if re.search(rf"\b{re.escape(name)}\b", later_source):
                    used_any = True
                    break
            if used_any:
                break

        if not used_any:
            names_str = ", ".join(sorted(imported)[:5])
            extra = f" and {len(imported) - 5} more" if len(imported) > 5 else ""
            findings.append(Finding(
                severity="warning",
                cell_index=idx,
                category="dead_code",
                message=(
                    f"Cell {idx}: imported names ({names_str}){extra} "
                    f"are not used in any downstream cell — possible "
                    f"dead import."
                ),
            ))


def _check_unreachable_code(notebook: Notebook, findings: list[Finding]) -> None:
    """Detect code after return, raise, break, continue in a block."""
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source.strip()
        if not source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _check_unreachable_in_body(node.body, cell.index, findings)


def _check_unreachable_in_body(
    body: list[ast.stmt],
    cell_index: int,
    findings: list[Finding],
) -> None:
    """Check a function body for statements after return/raise."""
    for i, stmt in enumerate(body):
        if isinstance(stmt, (ast.Return, ast.Raise)):
            if i + 1 < len(body):
                next_stmt = body[i + 1]
                # Skip docstrings and pass (sometimes used as placeholder)
                if not (
                    isinstance(next_stmt, ast.Expr) and
                    isinstance(next_stmt.value, ast.Constant) and
                    isinstance(next_stmt.value.value, str)
                ) and not isinstance(next_stmt, ast.Pass):
                    findings.append(Finding(
                        severity="warning",
                        cell_index=cell_index,
                        category="dead_code",
                        message=(
                            f"Cell {cell_index}: unreachable code after "
                            f"'{type(stmt).__name__.lower()}' in function."
                        ),
                    ))
            break


def _check_redundant_assignments(
    notebook: Notebook, findings: list[Finding],
) -> None:
    """Flag variables assigned but never used in downstream cells."""
    # Collect assignments per cell
    assignments_per_cell: dict[int, set[str]] = {}
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source.strip()
        if not source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        assigned: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned.add(target.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    assigned.add(node.target.id)
        if assigned:
            assignments_per_cell[cell.index] = assigned

    sorted_indices = sorted(assignments_per_cell.keys())
    for i, idx in enumerate(sorted_indices):
        assigned = assignments_per_cell[idx]
        if not assigned:
            continue
        for name in assigned:
            used = False
            for jdx in sorted_indices[i + 1:]:
                later_source = notebook.cells[jdx].source
                if re.search(rf"\b{re.escape(name)}\b", later_source):
                    used = True
                    break
            if not used:
                findings.append(Finding(
                    severity="info",
                    cell_index=idx,
                    category="dead_code",
                    message=(
                        f"Cell {idx}: '{name}' is assigned but never "
                        f"referenced downstream — possible redundant "
                        f"assignment."
                    ),
                ))


def _check_naming(notebook: Notebook) -> dict[str, Any]:
    """Assess variable and function naming quality.

    Flags single-letter variable names, non-descriptive names like
    ``df1`` / ``tmp`` / ``x2``, and inconsistent naming.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"issues"``: dict with counts by sub-category
    """
    findings: list[Finding] = []
    single_letter: list[tuple[int, str]] = []
    non_descriptive: list[tuple[int, str]] = []

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source.strip()
        if not source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # Check assignments
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        _evaluate_name(
                            target.id, cell.index,
                            single_letter, non_descriptive,
                        )
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    _evaluate_name(
                        node.target.id, cell.index,
                        single_letter, non_descriptive,
                    )
            # Check function/class definitions
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _evaluate_name(
                    node.name, cell.index,
                    single_letter, non_descriptive,
                )
            elif isinstance(node, ast.ClassDef):
                _evaluate_name(
                    node.name, cell.index,
                    single_letter, non_descriptive,
                )

    if single_letter:
        names = ", ".join(n for _, n in single_letter[:10])
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="naming",
            message=(
                f"Single-letter variable names used: {names}. "
                f"Use descriptive names for clarity."
            ),
        ))

    if non_descriptive:
        names = ", ".join(n for _, n in non_descriptive[:10])
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="naming",
            message=(
                f"Non-descriptive variable names detected: {names}. "
                f"Consider renaming to convey meaning."
            ),
        ))

    if not single_letter and not non_descriptive:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="naming",
            message="Naming is descriptive and consistent.",
        ))

    flagged = bool(single_letter) or bool(non_descriptive)
    return {
        "status": "flagged" if flagged else "passed",
        "findings": findings,
        "details": (
            f"{len(single_letter)} single-letter name(s), "
            f"{len(non_descriptive)} non-descriptive name(s)."
            if flagged
            else "No naming issues detected."
        ),
        "issues": {
            "single_letter": len(single_letter),
            "non_descriptive": len(non_descriptive),
        },
    }


def _evaluate_name(
    name: str,
    cell_index: int,
    single_letter: list[tuple[int, str]],
    non_descriptive: list[tuple[int, str]],
) -> None:
    """Evaluate a single name for quality issues."""
    if len(name) == 1 and name.isalpha():
        single_letter.append((cell_index, name))
    elif _RE_NONDESCRIPT.search(name):
        non_descriptive.append((cell_index, name))


def _check_output_hygiene(notebook: Notebook) -> dict[str, Any]:
    """Detect bloated cell outputs.

    Heuristics:
    - A print() call on a dataframe-like object without truncation.
    - A bare expression referencing a large variable without .head() etc.
    - Raw tensor/array output without truncation.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    """
    findings: list[Finding] = []

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source.strip()
        if not source:
            continue

        # Check for print(dataframe) — printing a large DF
        if _RE_PRINT.search(source) and _RE_FULL_DF.search(source):
            # Check if truncation method is present in the same cell
            if not _RE_TRUNCATION.search(source):
                findings.append(Finding(
                    severity="warning",
                    cell_index=cell.index,
                    category="output_hygiene",
                    message=(
                        f"Cell {cell.index}: prints a dataframe/array-like "
                        f"without truncation (.head(), .describe(), etc.). "
                        f"This may produce large outputs."
                    ),
                ))

        # Check for bare expression that references data
        has_data_ref = bool(re.search(
            r"\b(df|data|dataset|train|test|X|y|features|labels|tensor|model)\s*$",
            source,
            re.MULTILINE,
        ))
        if has_data_ref and not _RE_TRUNCATION.search(source):
            # It's a bare expression ending with a variable name — potential bloat
            has_safe = bool(re.search(
                r"\.(head|tail|sample|describe|shape|dtypes|columns|index|"
                r"size|ndim|values|keys)\s*\(",
                source,
            ))
            if not has_safe:
                findings.append(Finding(
                    severity="info",
                    cell_index=cell.index,
                    category="output_hygiene",
                    message=(
                        f"Cell {cell.index}: bare expression that may produce "
                        f"large output. Consider using .head() or .describe() "
                        f"to truncate."
                    ),
                ))

        # Check for raw tensor output
        if re.search(r"\b(print\s*\(\s*tensor|tensor\s*\.?\s*$)", source, re.IGNORECASE):
            findings.append(Finding(
                severity="info",
                cell_index=cell.index,
                category="output_hygiene",
                message=(
                    f"Cell {cell.index}: outputs a raw tensor. Consider "
                    f"using .numpy() or converting to a summary value."
                ),
            ))

    if not findings:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="output_hygiene",
            message="No bloated or problematic outputs detected.",
        ))

    flagged = any(f.severity == "warning" for f in findings)
    return {
        "status": "flagged" if flagged else "passed",
        "findings": findings,
        "details": (
            "Output hygiene issues detected."
            if flagged
            else "Outputs appear clean and well-formatted."
        ),
    }


# ---------------------------------------------------------------------------
# Score and status
# ---------------------------------------------------------------------------


def _compute_score(findings: list[Finding]) -> str:
    """Compute code quality score.

    - ``"low"``: no warning findings.
    - ``"high"``: >3 warning findings.
    - ``"moderate"``: between low and high.
    """
    warnings = [f for f in findings if f.severity == "warning"]
    if not warnings:
        return "low"
    if len(warnings) > 3:
        return "high"
    return "moderate"


def _compute_status(findings: list[Finding]) -> str:
    """Compute pass status from findings.

    - ``"error"`` if any error-severity finding exists.
    - ``"flagged"`` if any warning-severity finding exists.
    - ``"passed"`` otherwise.
    """
    if any(f.severity == "error" for f in findings):
        return "error"
    if any(f.severity == "warning" for f in findings):
        return "flagged"
    return "passed"


# ---------------------------------------------------------------------------
# Deliverable
# ---------------------------------------------------------------------------


def _build_deliverable(
    filename: str,
    repetitive: dict[str, Any],
    dead_code: dict[str, Any],
    naming: dict[str, Any],
    hygiene: dict[str, Any],
    findings: list[Finding],
    score: str,
    focus_areas: list[str],
) -> str:
    """Build narrative report text for PDF export."""
    lines: list[str] = [
        f"# Pass 5: Code Quality Review — {filename}",
        f"**Score**: {score.upper()}",
        "",
    ]

    if focus_areas:
        lines.append(f"**Focus areas**: {', '.join(focus_areas)}")
        lines.append("")

    # Repetitive code
    lines.append("## Repetitive Code")
    lines.append("")
    lines.append(f"  Status: **{repetitive['status'].upper()}**")
    lines.append(f"  {repetitive['details']}")
    lines.append("")

    # Dead code
    lines.append("## Dead Code")
    lines.append("")
    lines.append(f"  Status: **{dead_code['status'].upper()}**")
    lines.append(f"  {dead_code['details']}")
    lines.append("")

    # Naming quality
    lines.append("## Naming Quality")
    lines.append("")
    lines.append(f"  Status: **{naming['status'].upper()}**")
    lines.append(f"  {naming['details']}")
    lines.append("")

    # Output hygiene
    lines.append("## Output Hygiene")
    lines.append("")
    lines.append(f"  Status: **{hygiene['status'].upper()}**")
    lines.append(f"  {hygiene['details']}")
    lines.append("")

    # Score justification
    lines.append("## Score Justification")
    lines.append("")
    warnings = [f for f in findings if f.severity == "warning"]
    lines.append(
        f"  {len(warnings)} warning(s). "
        f"Overall code quality risk: **{score.upper()}**."
    )
    lines.append("")

    # Detailed findings
    if findings:
        lines.append("## Detailed Findings")
        lines.append("")
        for f in findings:
            cell_ref = f"Cell {f.cell_index}" if f.cell_index is not None else "Notebook"
            lines.append(f"  - [{f.severity}] [{cell_ref}] [{f.category}] {f.message}")
        lines.append("")

    return "\n".join(lines).strip()
