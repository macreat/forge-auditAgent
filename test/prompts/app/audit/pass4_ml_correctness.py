"""Pass 4: ML Correctness Audit — evaluation metrics, cross-validation
integrity, hyperparameter tuning boundaries, and baseline comparison.

Assesses the ML methodology used in the notebook by checking: whether
the chosen evaluation metric is appropriate for the task and class
distribution, whether cross-validation folds preserve train/test
separation, whether hyperparameter tuning is confined to training/CV
data, and whether a meaningful baseline comparison is reported.
"""

from __future__ import annotations

import re
from typing import Any

from app.audit.models import Cell, Finding, Notebook, PassResult

_PASS_NAME = "ML Correctness Audit"
_PASS_NUMBER = 4

# Metric detection patterns
_RE_ACCURACY = re.compile(r"\baccuracy[_a-z]*\b", re.IGNORECASE)
_RE_F1 = re.compile(r"\bf1[_a-z]*\b", re.IGNORECASE)
_RE_ROC_AUC = re.compile(r"\broc_?auc\b", re.IGNORECASE)
_RE_PRECISION = re.compile(r"\bprecision[_a-z]*\b", re.IGNORECASE)
_RE_RECALL = re.compile(r"\brecall[_a-z]*\b", re.IGNORECASE)
_RE_MSE = re.compile(r"\bmean_squared_error\b|\bmse\b", re.IGNORECASE)
_RE_R2 = re.compile(r"\br2[_a-z]*\b", re.IGNORECASE)

# Imbalance indicators
_RE_CLASS_IMBALANCE = re.compile(
    r"\b(imbalance|class_weight|stratify|smote|adasyn|"
    r"balanced_accuracy|balanced\s*dataset)\b",
    re.IGNORECASE,
)

# Cross-validation patterns
_RE_CROSS_VAL_SCORE = re.compile(r"cross_val_score\s*\(")
_RE_CROSS_VAL_PREDICT = re.compile(r"cross_val_predict\s*\(")
_RE_CROSS_VAL = re.compile(r"cross_val_\w+\s*\(")
_RE_KFOLD = re.compile(r"(KFold|StratifiedKFold|RepeatedKFold)\s*\(")

# Tuning patterns
_RE_GRID_SEARCH = re.compile(r"GridSearchCV\s*\(")
_RE_RANDOM_SEARCH = re.compile(r"RandomizedSearchCV\s*\(")
_RE_PARAM_GRID = re.compile(r"param_grid\s*=|params\s*=")

# Baseline patterns
_RE_DUMMY_CLF = re.compile(r"DummyClassifier\s*\(|DummyRegressor\s*\(")
_RE_SIMPLE_BASELINE = re.compile(
    r"\b(baseline|naive|dummy|trivial|simple_model|"
    r"majority_class|zero_rule)\b",
    re.IGNORECASE,
)
_RE_BENCHMARK = re.compile(r"\bbenchmark\b", re.IGNORECASE)

# Train/test split reference
_RE_TRAIN_TEST_SPLIT = re.compile(r"train_test_split\s*\(")
_RE_X_TRAIN = re.compile(r"\bx_train\b", re.IGNORECASE)
_RE_X_TEST = re.compile(r"\bx_test\b", re.IGNORECASE)
_RE_TEST_REF = re.compile(r"\btest\s*(?:set|data|split)\b", re.IGNORECASE)


def run(
    notebook: Notebook,
    focus_areas: list[str] | None = None,
) -> PassResult:
    """Execute Pass 4: ML Correctness Audit.

    Evaluates:
    - Whether the chosen evaluation metric(s) are appropriate for the
      task and class distribution.
    - Whether cross-validation operates on training data only.
    - Whether hyperparameter tuning avoids touching the held-out test set.
    - Whether model performance is reported alongside a baseline.

    Args:
        notebook: The parsed notebook to analyse.
        focus_areas: Optional focus area list.

    Returns:
        A :class:`PassResult` with status and score.
    """
    findings: list[Finding] = []

    metric_result = _check_metrics(notebook)
    findings.extend(metric_result["findings"])

    cv_result = _check_cv_integrity(notebook)
    findings.extend(cv_result["findings"])

    tuning_result = _check_tuning_boundary(notebook)
    findings.extend(tuning_result["findings"])

    baseline_result = _check_baseline(notebook)
    findings.extend(baseline_result["findings"])

    score = _compute_score(metric_result, cv_result, tuning_result, baseline_result)
    status = _compute_status(findings)

    deliverable = _build_deliverable(
        notebook.filename,
        metric_result,
        cv_result,
        tuning_result,
        baseline_result,
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


def _check_metrics(notebook: Notebook) -> dict[str, Any]:
    """Identify evaluation metrics and assess appropriateness.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"`` | ``"skipped"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"metrics_found"``: list of metric names detected
    """
    findings: list[Finding] = []
    metrics_found: set[str] = set()
    has_accuracy = False
    has_imbalance = False
    has_classification = False
    has_regression = False

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source

        if _RE_ACCURACY.search(st):
            metrics_found.add("accuracy")
            has_accuracy = True
            has_classification = True
        if _RE_F1.search(st):
            metrics_found.add("f1")
            has_classification = True
        if _RE_ROC_AUC.search(st):
            metrics_found.add("roc_auc")
            has_classification = True
        if _RE_PRECISION.search(st):
            metrics_found.add("precision")
            has_classification = True
        if _RE_RECALL.search(st):
            metrics_found.add("recall")
            has_classification = True
        if _RE_MSE.search(st):
            metrics_found.add("mse")
            has_regression = True
        if _RE_R2.search(st):
            metrics_found.add("r2")
            has_regression = True

        if _RE_CLASS_IMBALANCE.search(st):
            has_imbalance = True
        if re.search(
            r"\b(classification|classifier|LogisticRegression|RandomForest"
            r"Classifier|XGBClassifier)\b", st,
        ):
            has_classification = True
        if re.search(
            r"\b(regression|Regressor|LinearRegression|RandomForestRegressor"
            r"|XGBRegressor)\b", st,
        ):
            has_regression = True

    if not metrics_found:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="metrics",
            message=(
                "No standard evaluation metrics detected. The notebook "
                "may not report quantitative performance."
            ),
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No metrics detected.",
            "metrics_found": [],
        }

    # Check accuracy on imbalanced data
    if has_accuracy and has_classification and not has_imbalance:
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="metrics",
            message=(
                "Accuracy is used on what appears to be a classification "
                "task, but no class imbalance handling (class_weight, "
                "stratify, SMOTE, etc.) was detected. Accuracy can be "
                "misleading on imbalanced data."
            ),
        ))

    # If accuracy is the ONLY metric for classification with imbalance detected
    if has_accuracy and has_classification and has_imbalance:
        other_metrics = metrics_found - {"accuracy"}
        if not other_metrics:
            findings.append(Finding(
                severity="warning",
                cell_index=None,
                category="metrics",
                message=(
                    "Accuracy is the sole metric on a task where class "
                    "imbalance handling was used. Consider also reporting "
                    "F1-score, ROC-AUC, precision, or recall for a more "
                    "complete picture."
                ),
            ))

    if not findings:
        metric_list = ", ".join(sorted(metrics_found))
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="metrics",
            message=(
                f"Metrics detected: {metric_list}. Appropriate range of "
                f"metrics for the task."
            ),
        ))

    return {
        "status": "flagged" if any(
            f.severity == "warning" for f in findings
        ) else "passed",
        "findings": findings,
        "details": f"Metrics found: {', '.join(sorted(metrics_found))}.",
        "metrics_found": sorted(metrics_found),
    }


def _check_cv_integrity(notebook: Notebook) -> dict[str, Any]:
    """Verify cross-validation uses training data, not full/test data.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"`` | ``"skipped"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"cv_method"``: detected CV method or ``None``
    """
    findings: list[Finding] = []
    cv_method: str | None = None
    cv_cell: int | None = None
    split_cell: int | None = None

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source

        if cv_method is None:
            if _RE_CROSS_VAL_SCORE.search(st):
                cv_method = "cross_val_score"
                cv_cell = cell.index
            elif _RE_CROSS_VAL_PREDICT.search(st):
                cv_method = "cross_val_predict"
                cv_cell = cell.index
            elif _RE_KFOLD.search(st):
                cv_method = "KFold / manual CV"
                cv_cell = cell.index

        if split_cell is None and _RE_TRAIN_TEST_SPLIT.search(st):
            split_cell = cell.index

    if cv_method is None:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="cv_integrity",
            message="No cross-validation call detected — CV check skipped.",
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No CV mechanism found.",
            "cv_method": None,
        }

    # Warn if CV is used before train_test_split (possible full-data CV)
    if split_cell is not None and cv_cell is not None and cv_cell < split_cell:
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="cv_integrity",
            message=(
                f"Cross-validation ({cv_method}) at cell {cv_cell} occurs "
                f"before train_test_split at cell {split_cell}. If CV operates "
                f"on the full unsplit dataset, this may leak information."
            ),
        ))
        return {
            "status": "flagged",
            "findings": findings,
            "details": f"CV ({cv_method}) before split — potential leakage.",
            "cv_method": cv_method,
        }

    findings.append(Finding(
        severity="info",
        cell_index=None,
        category="cv_integrity",
        message=(
            f"Cross-validation detected ({cv_method}) and "
            f"{'no train_test_split found — CV appears to be the validation strategy' if split_cell is None else 'operates after the data split — CV integrity looks sound'}."
        ),
    ))
    return {
        "status": "passed",
        "findings": findings,
        "details": f"CV method: {cv_method}.",
        "cv_method": cv_method,
    }


def _check_tuning_boundary(notebook: Notebook) -> dict[str, Any]:
    """Confirm hyperparameter tuning uses training/CV data only.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"`` | ``"skipped"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"tuning_method"``: detected tuning method or ``None``
    """
    findings: list[Finding] = []
    tuning_method: str | None = None
    tuning_cell: int | None = None
    test_refs_in_tuning: list[int] = []

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source

        if tuning_method is None:
            if _RE_GRID_SEARCH.search(st):
                tuning_method = "GridSearchCV"
                tuning_cell = cell.index
            elif _RE_RANDOM_SEARCH.search(st):
                tuning_method = "RandomizedSearchCV"
                tuning_cell = cell.index
            elif _RE_PARAM_GRID.search(st) and "search" in st.lower():
                tuning_method = "Manual parameter search"
                tuning_cell = cell.index

        # Check for test data references in tuning cells
        if tuning_cell is not None and cell.index >= tuning_cell:
            # Only check cells after tuning is found
            has_test_var = bool(_RE_X_TEST.search(st))
            has_test_ref = bool(_RE_TEST_REF.search(st))
            # But exclude the test/train split call itself and test/evaluation cells
            is_eval = bool(re.search(r"(score|predict|evaluate)", st, re.IGNORECASE))
            if has_test_var and is_eval:
                # This is likely evaluation, not tuning leakage
                pass
            elif has_test_var and _RE_X_TRAIN.search(st):
                # Both train and test references are normal
                pass
            elif has_test_ref and not _RE_X_TRAIN.search(st):
                test_refs_in_tuning.append(cell.index)

    if tuning_method is None:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="tuning_boundary",
            message=(
                "No hyperparameter tuning (GridSearchCV, RandomizedSearchCV, "
                "manual param search) detected — tuning boundary check skipped."
            ),
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No tuning detected.",
            "tuning_method": None,
        }

    if test_refs_in_tuning:
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="tuning_boundary",
            message=(
                f"Test data references found in cell(s) {test_refs_in_tuning} "
                f"around tuning area ({tuning_method}). Ensure the held-out "
                f"test set was not used for hyperparameter decisions."
            ),
        ))
        return {
            "status": "flagged",
            "findings": findings,
            "details": f"Tuning ({tuning_method}) with possible test-set references.",
            "tuning_method": tuning_method,
        }

    findings.append(Finding(
        severity="info",
        cell_index=None,
        category="tuning_boundary",
        message=(
            f"Hyperparameter tuning ({tuning_method}) detected with no "
            f"obvious test-set references — tuning appears confined to "
            f"training/CV data."
        ),
    ))
    return {
        "status": "passed",
        "findings": findings,
        "details": f"Tuning: {tuning_method}, no test-set leakage detected.",
        "tuning_method": tuning_method,
    }


def _check_baseline(notebook: Notebook) -> dict[str, Any]:
    """Detect whether model performance is reported alongside a baseline.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"`` | ``"skipped"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    """
    findings: list[Finding] = []
    has_dummy = False
    has_baseline_keyword = False
    has_benchmark = False
    baseline_cells: list[int] = []

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source

        if _RE_DUMMY_CLF.search(st):
            has_dummy = True
            baseline_cells.append(cell.index)
        if _RE_SIMPLE_BASELINE.search(st):
            has_baseline_keyword = True
            baseline_cells.append(cell.index)
        if _RE_BENCHMARK.search(st):
            has_benchmark = True
            baseline_cells.append(cell.index)

    if has_dummy or has_baseline_keyword or has_benchmark:
        refs = []
        if has_dummy:
            refs.append("DummyClassifier/Regressor")
        if has_baseline_keyword:
            refs.append("baseline/simple model reference")
        if has_benchmark:
            refs.append("benchmark mention")
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="baseline",
            message=f"Baseline comparison present: {', '.join(refs)}.",
        ))
        return {
            "status": "passed",
            "findings": findings,
            "details": f"Baseline detected: {', '.join(refs)}.",
        }

    # Check if the notebook has any model training at all
    has_model = bool(
        sum(
            1 for c in notebook.cells
            if c.cell_type == "code"
            and re.search(
                r"\b(fit|train|predict|score)\s*\(",
                c.source,
            )
        )
    )

    if not has_model:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="baseline",
            message=(
                "No model training detected — baseline comparison not applicable."
            ),
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No model training found.",
        }

    findings.append(Finding(
        severity="warning",
        cell_index=None,
        category="baseline",
        message=(
            "Model performance is reported without a baseline comparison "
            "(DummyClassifier, simple model, or benchmark). Adding a "
            "baseline helps contextualise whether the model adds value "
            "over naive strategies."
        ),
    ))
    return {
        "status": "flagged",
        "findings": findings,
        "details": "No baseline comparison detected.",
    }


# ---------------------------------------------------------------------------
# Score and status
# ---------------------------------------------------------------------------


def _compute_score(
    metric: dict[str, Any],
    cv: dict[str, Any],
    tuning: dict[str, Any],
    baseline: dict[str, Any],
) -> str:
    """Compute overall ML correctness score.

    - ``"low"``: all applicable sub-checks pass.
    - ``"high"``: at least 2 sub-checks flagged with warnings.
    - ``"moderate"``: mixed results.
    """
    flagged = 0
    for result in (metric, cv, tuning, baseline):
        if result["status"] == "flagged":
            flagged += 1

    if flagged == 0:
        return "low"
    if flagged >= 2:
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
    metric: dict[str, Any],
    cv: dict[str, Any],
    tuning: dict[str, Any],
    baseline: dict[str, Any],
    findings: list[Finding],
    score: str,
    focus_areas: list[str],
) -> str:
    """Build narrative report text for PDF export."""
    lines: list[str] = [
        f"# Pass 4: ML Correctness Audit — {filename}",
        f"**Score**: {score.upper()}",
        "",
    ]

    if focus_areas:
        lines.append(f"**Focus areas**: {', '.join(focus_areas)}")
        lines.append("")

    # Evaluation metrics
    lines.append("## Evaluation Metrics")
    lines.append("")
    lines.append(f"  Status: **{metric['status'].upper()}**")
    lines.append(f"  {metric['details']}")
    lines.append("")

    # CV integrity
    lines.append("## Cross-Validation Integrity")
    lines.append("")
    lines.append(f"  Status: **{cv['status'].upper()}**")
    lines.append(f"  {cv['details']}")
    lines.append("")

    # Tuning boundary
    lines.append("## Hyperparameter Tuning Boundary")
    lines.append("")
    lines.append(f"  Status: **{tuning['status'].upper()}**")
    lines.append(f"  {tuning['details']}")
    lines.append("")

    # Baseline comparison
    lines.append("## Baseline Comparison")
    lines.append("")
    lines.append(f"  Status: **{baseline['status'].upper()}**")
    lines.append(f"  {baseline['details']}")
    lines.append("")

    # Score justification
    lines.append("## Score Justification")
    lines.append("")
    sub_flagged = sum(
        1 for r in [metric, cv, tuning, baseline]
        if r["status"] == "flagged"
    )
    sub_skipped = sum(
        1 for r in [metric, cv, tuning, baseline]
        if r["status"] == "skipped"
    )
    sub_total = 4
    lines.append(
        f"  {sub_flagged}/{sub_total} sub-check(s) flagged "
        f"({sub_skipped} skipped). "
        f"Overall ML correctness risk: **{score.upper()}**."
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
