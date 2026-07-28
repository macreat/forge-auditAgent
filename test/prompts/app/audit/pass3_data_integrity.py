"""Pass 3: Data Integrity Review — split ordering, data leakage, missing
data handling, and ingestion validation.

Examines the data pipeline in a notebook for ordering errors, data leakage
signs, consistent missing-data handling, and ingestion-time validation.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from app.audit.models import Cell, Finding, Notebook, PassResult

_PASS_NAME = "Data Integrity Review"
_PASS_NUMBER = 3

# Regex patterns
_RE_TRAIN_TEST_SPLIT = re.compile(r"train_test_split\s*\(")
_RE_STANDARD_SCALER = re.compile(r"StandardScaler\(\)")
_RE_MINMAX_SCALER = re.compile(r"MinMaxScaler\(\)")
_RE_GET_DUMMIES = re.compile(r"pd\.get_dummies|pandas\.get_dummies")
_RE_IMPUTER = re.compile(r"(SimpleImputer|IterativeImputer|KNNImputer)\(\)")
_RE_ENCODING = re.compile(r"(LabelEncoder|OneHotEncoder|OrdinalEncoder)\(\)")
_RE_FIT_CALL = re.compile(r"\.fit\s*\(")
_RE_LOAD_CSV = re.compile(r"(?:pd|pandas)\.read_csv\s*\(")
_RE_DTYPES = re.compile(r"\.dtypes\b")
_RE_SHAPE = re.compile(r"\.shape\b")
_RE_INFO = re.compile(r"\.info\(\)")
_RE_ISNULL_SUM = re.compile(r"\.isnull\(\)\.sum\(\)")
_RE_ISNULL_ANY = re.compile(r"\.isnull\(\)\.any\(\)")


def run(
    notebook: Notebook,
    focus_areas: list[str] | None = None,
) -> PassResult:
    """Execute Pass 3: Data Integrity Review.

    Checks:
    - ``train_test_split`` ordering relative to preprocessing steps.
    - Data leakage from ``fit()`` calls on full dataset before split.
    - Missing data imputation strategy and cross-split consistency.
    - Ingestion-time validation (``.dtypes``, ``.shape``, ``.info()``,
      ``.isnull().sum()``).

    Args:
        notebook: The parsed notebook to analyse.
        focus_areas: Optional focus area list.

    Returns:
        A :class:`PassResult` with status and score.
    """
    findings: list[Finding] = []

    split_result = _check_split_ordering(notebook)
    findings.extend(split_result["findings"])

    leakage_result = _check_data_leakage(notebook)
    findings.extend(leakage_result["findings"])

    missing_result = _check_missing_data(notebook)
    findings.extend(missing_result["findings"])

    ingestion_result = _check_ingestion_validation(notebook)
    findings.extend(ingestion_result["findings"])

    score = _compute_score(findings)
    status = _compute_status(findings)

    deliverable = _build_deliverable(
        notebook.filename, split_result, leakage_result,
        missing_result, ingestion_result, findings, score,
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


def _check_split_ordering(notebook: Notebook) -> dict[str, Any]:
    """Verify that ``train_test_split`` is called *before* preprocessing.

    Returns:
        Dict with ``status``, ``findings``, ``details``, and
        ``split_cell_index`` / ``preprocessing_cell_index``.
    """
    findings: list[Finding] = []
    split_cell: int | None = None
    preproc_cells: list[int] = []

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source

        if _RE_TRAIN_TEST_SPLIT.search(st) and split_cell is None:
            split_cell = cell.index

        for pat in [_RE_STANDARD_SCALER, _RE_MINMAX_SCALER,
                     _RE_GET_DUMMIES, _RE_IMPUTER, _RE_ENCODING]:
            if pat.search(st):
                preproc_cells.append(cell.index)

    if split_cell is None:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="split_ordering",
            message="No train_test_split call detected — skip ordering check.",
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No train_test_split found — ordering not applicable.",
        }

    # Check that all preprocessing happens at or after the split
    misplaced = [pc for pc in preproc_cells if pc < split_cell]
    if misplaced:
        findings.append(Finding(
            severity="error",
            cell_index=None,
            category="split_ordering",
            message=(
                f"train_test_split at cell {split_cell} but preprocessing "
                f"occurs in earlier cell(s): {misplaced}. "
                f"Preprocessing should happen AFTER the split to avoid "
                f"data leakage."
            ),
        ))
        return {
            "status": "flagged",
            "findings": findings,
            "details": f"Split at cell {split_cell}, preprocessing at {misplaced}.",
            "split_cell_index": split_cell,
            "preprocessing_cell_index": misplaced,
        }

    findings.append(Finding(
        severity="info",
        cell_index=split_cell,
        category="split_ordering",
        message=(
            f"train_test_split at cell {split_cell} occurs before "
            f"preprocessing steps."
        ),
    ))
    return {
        "status": "passed",
        "findings": findings,
        "details": f"Split at cell {split_cell} occurs before preprocessing.",
        "split_cell_index": split_cell,
        "preprocessing_cell_index": None,
    }


def _check_data_leakage(notebook: Notebook) -> dict[str, Any]:
    """Flag ``.fit()`` calls on the full dataset before any split.

    Heuristic: if a ``.fit()`` call appears in a cell *before* the
    ``train_test_split`` cell, it may be fitting on the full dataset.
    """
    findings: list[Finding] = []
    split_cell: int | None = None

    # Find the first split call
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        if _RE_TRAIN_TEST_SPLIT.search(cell.source):
            split_cell = cell.index
            break

    fit_before_split: list[int] = []
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        if _RE_FIT_CALL.search(cell.source):
            if split_cell is None or cell.index < split_cell:
                fit_before_split.append(cell.index)

    if not fit_before_split:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="data_leakage",
            message="No fit() calls detected before split — no pipeline-level "
                    "leakage risk identified.",
        ))
        return {
            "status": "passed",
            "findings": findings,
            "details": "No fit() calls before split.",
        }

    findings.append(Finding(
        severity="warning",
        cell_index=None,
        category="data_leakage",
        message=(
            f"{len(fit_before_split)} .fit() call(s) in cell(s) "
            f"{fit_before_split} appear before the data split. If these "
            f"operate on the full dataset, they may cause data leakage."
        ),
    ))
    return {
        "status": "flagged",
        "findings": findings,
        "details": f"Fit calls before split: cells {fit_before_split}.",
        "fit_cells": fit_before_split,
    }


def _check_missing_data(notebook: Notebook) -> dict[str, Any]:
    """Check missing data handling: imputation detection and consistency.

    Flags:
    - Imputation called on a dataset that hasn't been split yet.
    - Multiple different imputation strategies used.
    """
    findings: list[Finding] = []
    imputation_cells: list[int] = []
    strategies: set[str] = set()

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source
        if _RE_IMPUTER.search(st):
            imputation_cells.append(cell.index)
            # Try to extract strategy
            m = re.search(r"strategy\s*=\s*['\"](.+?)['\"]", st)
            if m:
                strategies.add(m.group(1))

    if not imputation_cells:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="missing_data",
            message="No imputation detected — missing data check skipped.",
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No imputation steps found.",
            "strategies": [],
        }

    # Find split cell for ordering
    split_cell: int | None = None
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        if _RE_TRAIN_TEST_SPLIT.search(cell.source):
            split_cell = cell.index
            break

    unprepped = [c for c in imputation_cells if split_cell is not None and c < split_cell]
    if unprepped:
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="missing_data",
            message=(
                f"Imputation applied in cell(s) {unprepped}, which appear "
                f"before train_test_split (cell {split_cell}). This may leak "
                f"information from test into training data."
            ),
        ))

    if len(strategies) > 1:
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="missing_data",
            message=(
                f"Multiple imputation strategies detected: "
                f"{', '.join(sorted(strategies))}. Ensure consistency "
                f"across training and test pipelines."
            ),
        ))

    if not findings:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="missing_data",
            message="Imputation detected with consistent strategy.",
        ))

    details = (
        f"Imputation in {len(imputation_cells)} cell(s)"
        + (f"; strategies: {', '.join(sorted(strategies))}" if strategies else "")
        + "."
    )
    return {
        "status": "flagged" if any(f.severity == "warning" for f in findings) else "passed",
        "findings": findings,
        "details": details,
        "strategies": list(strategies),
    }


def _check_ingestion_validation(notebook: Notebook) -> dict[str, Any]:
    """Check whether data ingestion cells are followed by validation.

    After a ``pd.read_csv`` or similar data-load call, verifies that at
    least one of ``.dtypes``, ``.shape``, ``.info()``, or
    ``.isnull().sum()`` appears in the same or an immediately following
    cell.
    """
    findings: list[Finding] = []
    load_cell_indices: list[int] = []
    validated_cells: set[int] = set()

    # Find load cells
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        if _RE_LOAD_CSV.search(cell.source):
            load_cell_indices.append(cell.index)

    if not load_cell_indices:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="ingestion_validation",
            message="No pd.read_csv detected — ingestion validation check skipped.",
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No data-loading cells detected.",
        }

    # Find validation calls
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source
        if _RE_DTYPES.search(st) or _RE_SHAPE.search(st) or \
           _RE_INFO.search(st) or _RE_ISNULL_SUM.search(st) or \
           _RE_ISNULL_ANY.search(st):
            validated_cells.add(cell.index)

    unvalidated: list[int] = []
    for lc in load_cell_indices:
        # Check the loading cell itself or the next 2 cells
        nearby = {lc, lc + 1, lc + 2}
        if not nearby & validated_cells:
            unvalidated.append(lc)

    if unvalidated:
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="ingestion_validation",
            message=(
                f"Data loaded in cell(s) {unvalidated} without subsequent "
                f"validation (.dtypes, .shape, .info(), .isnull().sum()). "
                f"Add ingestion-time validation to catch structural issues "
                f"early."
            ),
        ))
        return {
            "status": "flagged",
            "findings": findings,
            "details": f"Unvalidated load(s) at cells {unvalidated}.",
        }

    findings.append(Finding(
        severity="info",
        cell_index=None,
        category="ingestion_validation",
        message="Data loading is followed by ingestion-time validation.",
    ))
    return {
        "status": "passed",
        "findings": findings,
        "details": "All data loads are validated.",
    }


# ---------------------------------------------------------------------------
# Score and status
# ---------------------------------------------------------------------------


def _compute_score(findings: list[Finding]) -> str:
    """Compute data integrity score.

    - ``"low"``: no error findings and at most 2 warning/info non-info findings.
    - ``"high"``: any error findings or more than 4 total findings.
    - ``"moderate"``: between low and high.
    """
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    total = len(errors) + len(warnings)

    if not errors and total <= 2:
        return "low"
    if errors or total > 4:
        return "high"
    return "moderate"


def _compute_status(findings: list[Finding]) -> str:
    """Compute pass status from findings.

    - ``"error"`` if any error-severity finding exists.
    - ``"flagged"`` if any warning-severity finding exists.
    - ``"passed"`` otherwise (info-only findings do not change status).
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
    split_result: dict[str, Any],
    leakage_result: dict[str, Any],
    missing_result: dict[str, Any],
    ingestion_result: dict[str, Any],
    findings: list[Finding],
    score: str,
    focus_areas: list[str],
) -> str:
    """Build narrative report text for PDF export."""
    lines: list[str] = [
        f"# Pass 3: Data Integrity Review — {filename}",
        f"**Score**: {score.upper()}",
        "",
    ]

    if focus_areas:
        lines.append(f"**Focus areas**: {', '.join(focus_areas)}")
        lines.append("")

    # Split ordering
    lines.append("## Split Ordering")
    lines.append("")
    lines.append(f"  Status: **{split_result['status'].upper()}**")
    lines.append(f"  {split_result['details']}")
    lines.append("")

    # Data leakage
    lines.append("## Data Leakage")
    lines.append("")
    lines.append(f"  Status: **{leakage_result['status'].upper()}**")
    lines.append(f"  {leakage_result['details']}")
    lines.append("")

    # Missing data
    lines.append("## Missing Data Handling")
    lines.append("")
    lines.append(f"  Status: **{missing_result['status'].upper()}**")
    lines.append(f"  {missing_result['details']}")
    lines.append("")

    # Ingestion validation
    lines.append("## Ingestion Validation")
    lines.append("")
    lines.append(f"  Status: **{ingestion_result['status'].upper()}**")
    lines.append(f"  {ingestion_result['details']}")
    lines.append("")

    # Score justification
    lines.append("## Score Justification")
    lines.append("")
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    lines.append(
        f"  {len(errors)} error(s), {len(warnings)} warning(s). "
        f"Overall data integrity risk: **{score.upper()}**."
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
