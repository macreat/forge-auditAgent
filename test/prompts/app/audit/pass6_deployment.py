"""Pass 6: Deployment Readiness — artifact versioning, inference/training
separation, resource documentation, environment completeness, and PII scan.

Assesses whether the notebook is suitable for production or publication by
checking: versioned artifact filenames, separable inference logic, documented
compute resources, complete environment exports, and absence of embedded
credentials or sensitive data.
"""

from __future__ import annotations

import re
from typing import Any

from app.audit.models import Cell, Finding, Notebook, PassResult

_PASS_NAME = "Deployment Readiness"
_PASS_NUMBER = 6

# Artifact versioning patterns
_RE_MODEL_SAVE = re.compile(r"\.(?:save|save_model|dump)\s*\(")
_RE_PLT_SAVEFIG = re.compile(r"plt\.savefig\s*\(|savefig\s*\(")
_RE_VERSIONED = re.compile(
    r"(?x)"
    r"(?:v\d+"
    r"|\d{4}[_-]\d{2}[_-]\d{2}"
    r"|timestamp|datetime|time\.strftime"
    r"|_v\d+|_latest|_prod|_staging"
    r")",
)
_RE_OVERWRITABLE = re.compile(
    r"(?x)"
    r"(?:"
    r"(?:model|checkpoint|weights)\.(?:pkl|pt|h5|onnx|joblib|pth)"
    r"|(?:plot|figure|chart|result|output|report)\.(?:png|pdf|svg|csv)"
    r")",
    re.IGNORECASE,
)

# Inference/training separation
_RE_MODEL_LOAD = re.compile(r"\.(?:load|load_model|load_weights|from_pretrained)\s*\(")
_RE_MODEL_PREDICT = re.compile(r"\.(?:predict|predict_proba|transform)\s*\(")
_RE_TRAIN_FIT = re.compile(r"\.(?:fit|train)\s*\(")

# Resource documentation
_RE_RAM = re.compile(r"\b(?:RAM|memory|GB|GiB)\b", re.IGNORECASE)
_RE_GPU = re.compile(r"\b(?:GPU|VRAM|CUDA|CUDA_VISIBLE_DEVICES)\b", re.IGNORECASE)
_RE_RUNTIME = re.compile(r"\b(?:runtime|~?\d+\s*(?:min|hour|sec))\b", re.IGNORECASE)

# Environment completeness
_RE_REQUIREMENTS = re.compile(r"requirements\.txt", re.IGNORECASE)
_RE_CONDA_YAML = re.compile(r"(?:environment|conda)\.(?:yaml|yml)", re.IGNORECASE)
_RE_PYPROJECT = re.compile(r"pyproject\.toml", re.IGNORECASE)

# PII patterns
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_RE_IP_ADDRESS = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
_RE_CREDENTIAL = re.compile(
    r"(?:api[_-]?key|password|secret|token|auth[_-]?token)\s*=\s*['\"](.+?)['\"]",
    re.IGNORECASE,
)
_RE_AWS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")
_RE_SSH_KEY = re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY-----")


def run(
    notebook: Notebook,
    focus_areas: list[str] | None = None,
) -> PassResult:
    """Execute Pass 6: Deployment Readiness.

    Assesses:
    - Whether model artifacts are saved with versioned/timestamped filenames.
    - Whether inference logic is separable from training (model-load path).
    - Whether compute resources (RAM, GPU, runtime) are documented.
    - Whether a complete environment export (requirements.txt, conda.yaml)
      is present.
    - Whether PII (emails, IPs, credentials) is embedded in source cells.

    Args:
        notebook: The parsed notebook to analyse.
        focus_areas: Optional focus area list.

    Returns:
        A :class:`PassResult` with status and score.
    """
    findings: list[Finding] = []

    versioning_result = _check_artifact_versioning(notebook)
    findings.extend(versioning_result["findings"])

    separation_result = _check_inference_separation(notebook)
    findings.extend(separation_result["findings"])

    resources_result = _check_resource_docs(notebook)
    findings.extend(resources_result["findings"])

    env_result = _check_environment(notebook)
    findings.extend(env_result["findings"])

    pii_result = _check_pii(notebook)
    findings.extend(pii_result["findings"])

    score = _compute_score(
        versioning_result, separation_result,
        resources_result, env_result, pii_result,
    )
    status = _compute_status(findings)

    deliverable = _build_deliverable(
        notebook.filename,
        versioning_result,
        separation_result,
        resources_result,
        env_result,
        pii_result,
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


def _check_artifact_versioning(notebook: Notebook) -> dict[str, Any]:
    """Detect whether model artifacts are versioned or overwritable.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"`` | ``"skipped"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"versioned"``: list of (cell, description)
    - ``"overwritable"``: list of (cell, description)
    """
    findings: list[Finding] = []
    versioned: list[tuple[int, str]] = []
    overwritable: list[tuple[int, str]] = []

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source

        if not _RE_MODEL_SAVE.search(st) and not _RE_PLT_SAVEFIG.search(st):
            continue

        if _RE_VERSIONED.search(st):
            versioned.append((
                cell.index,
                "Versioned filename detected in save call.",
            ))
        elif _RE_OVERWRITABLE.search(st):
            overwritable.append((
                cell.index,
                "Overwritable fixed filename detected.",
            ))
        else:
            overwritable.append((
                cell.index,
                "Save call without versioning or timestamp.",
            ))

    if not versioned and not overwritable:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="artifact_versioning",
            message=(
                "No model or plot save calls detected -- versioning "
                "check not applicable."
            ),
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No save calls found.",
            "versioned": [],
            "overwritable": [],
        }

    if overwritable:
        for idx, desc in overwritable:
            findings.append(Finding(
                severity="warning",
                cell_index=idx,
                category="artifact_versioning",
                message=f"Cell {idx}: {desc}",
            ))
        details = f"{len(overwritable)} unversioned save(s) detected."
    else:
        details = "All artifacts use versioned or timestamped filenames."

    if versioned:
        for idx, desc in versioned:
            findings.append(Finding(
                severity="info",
                cell_index=idx,
                category="artifact_versioning",
                message=f"Cell {idx}: {desc}",
            ))

    status = "flagged" if overwritable else "passed"
    return {
        "status": status,
        "findings": findings,
        "details": details,
        "versioned": versioned,
        "overwritable": overwritable,
    }


def _check_inference_separation(notebook: Notebook) -> dict[str, Any]:
    """Check whether inference logic is separable from training.

    Heuristic: if a model-load call (load, load_model, from_pretrained)
    exists separately from training/fit cells, inference is considered
    separable.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"`` | ``"skipped"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    """
    findings: list[Finding] = []
    has_train = False
    has_load = False
    has_predict = False
    train_cells: list[int] = []
    load_cells: list[int] = []
    predict_cells: list[int] = []

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source

        if _RE_TRAIN_FIT.search(st):
            has_train = True
            train_cells.append(cell.index)
        if _RE_MODEL_LOAD.search(st):
            has_load = True
            load_cells.append(cell.index)
        if _RE_MODEL_PREDICT.search(st):
            has_predict = True
            predict_cells.append(cell.index)

    if not has_train and not has_load and not has_predict:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="inference_separation",
            message=(
                "No model training, loading, or prediction detected -- "
                "separation check not applicable."
            ),
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No model-related code detected.",
        }

    if has_load and has_predict:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="inference_separation",
            message=(
                f"Model load cells ({load_cells}) and prediction cells "
                f"({predict_cells}) detected -- inference logic appears "
                f"separable from training."
            ),
        ))
        return {
            "status": "passed",
            "findings": findings,
            "details": "Load -> predict path exists; inference is separable.",
        }

    if has_train and has_predict and not has_load:
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="inference_separation",
            message=(
                "Training and prediction cells are present but no model "
                "load path (.load(), .load_model(), from_pretrained) exists. "
                "Prediction appears to require re-running training."
            ),
        ))
        return {
            "status": "flagged",
            "findings": findings,
            "details": "No model-load path; inference depends on training.",
        }

    findings.append(Finding(
        severity="info",
        cell_index=None,
        category="inference_separation",
        message="Model operations detected without clear train/predict separation.",
    ))
    return {
        "status": "passed",
        "findings": findings,
        "details": "Model code present with basic separation.",
    }


def _check_resource_docs(notebook: Notebook) -> dict[str, Any]:
    """Check for compute resource documentation in markdown cells.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"`` | ``"skipped"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"resources_found"``: list of resource categories
    """
    findings: list[Finding] = []
    resources_found: set[str] = set()

    for cell in notebook.cells:
        source = cell.source
        if cell.cell_type == "markdown":
            if _RE_RAM.search(source):
                resources_found.add("RAM/memory")
            if _RE_GPU.search(source):
                resources_found.add("GPU/VRAM")
            if _RE_RUNTIME.search(source):
                resources_found.add("runtime estimate")
        elif cell.cell_type == "code":
            comment_lines = [
                ln for ln in source.split("\n")
                if ln.strip().startswith("#")
            ]
            comment_text = " ".join(comment_lines)
            if _RE_RAM.search(comment_text):
                resources_found.add("RAM/memory (in code comment)")
            if _RE_GPU.search(comment_text):
                resources_found.add("GPU/VRAM (in code comment)")
            if _RE_RUNTIME.search(comment_text):
                resources_found.add("runtime estimate (in code comment)")

    if resources_found:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="resource_docs",
            message=(
                f"Compute resources documented: "
                f"{', '.join(sorted(resources_found))}."
            ),
        ))
        return {
            "status": "passed",
            "findings": findings,
            "details": f"Resources documented: {', '.join(sorted(resources_found))}.",
            "resources_found": sorted(resources_found),
        }

    has_compute = bool(
        sum(
            1 for c in notebook.cells
            if c.cell_type == "code"
            and re.search(
                r"\b(GPU|CUDA|\.fit\s*\(|train|model|tensorflow|torch)\b",
                c.source,
            )
        )
    )

    if not has_compute:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="resource_docs",
            message="No compute-intensive operations detected -- resource docs not applicable.",
        ))
        return {
            "status": "skipped",
            "findings": findings,
            "details": "No compute-intensive code detected.",
            "resources_found": [],
        }

    findings.append(Finding(
        severity="warning",
        cell_index=None,
        category="resource_docs",
        message=(
            "Compute resources (RAM, GPU, VRAM, expected runtime) "
            "are not documented in markdown or comments. Consider "
            "adding hardware requirements for reproducibility."
        ),
    ))
    return {
        "status": "flagged",
        "findings": findings,
        "details": "No resource documentation found.",
        "resources_found": [],
    }


def _check_environment(notebook: Notebook) -> dict[str, Any]:
    """Check for environment export files referenced in the notebook.

    Scans markdown cells for requirements.txt, conda.yaml/environment.yml,
    or pyproject.toml references.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"env_files"``: list of file types found
    """
    findings: list[Finding] = []
    env_files: set[str] = set()

    for cell in notebook.cells:
        source = cell.source
        if _RE_REQUIREMENTS.search(source):
            env_files.add("requirements.txt")
        if _RE_CONDA_YAML.search(source):
            env_files.add("conda/environment.yaml")
        if _RE_PYPROJECT.search(source):
            env_files.add("pyproject.toml")

    if env_files:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="environment",
            message=(
                f"Environment export(s) referenced: "
                f"{', '.join(sorted(env_files))}."
            ),
        ))
        return {
            "status": "passed",
            "findings": findings,
            "details": f"Env files: {', '.join(sorted(env_files))}.",
            "env_files": sorted(env_files),
        }

    findings.append(Finding(
        severity="warning",
        cell_index=None,
        category="environment",
        message=(
            "No environment export file (requirements.txt, conda.yaml, "
            "pyproject.toml) referenced in the notebook. A complete env "
            "export ensures deployment parity."
        ),
    ))
    return {
        "status": "flagged",
        "findings": findings,
        "details": "No environment export referenced.",
        "env_files": [],
    }


def _check_pii(notebook: Notebook) -> dict[str, Any]:
    """Scan for PII: emails, IP addresses, credentials, API keys.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    """
    findings: list[Finding] = []

    email_count = 0
    ip_count = 0
    cred_count = 0
    aws_count = 0
    ssh_count = 0

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        st = cell.source

        # Emails
        for match in _RE_EMAIL.finditer(st):
            email = match.group(0)
            # Skip synthetic emails like user@example.com or placeholder
            if "example.com" not in email and "test.com" not in email:
                email_count += 1
                findings.append(Finding(
                    severity="warning",
                    cell_index=cell.index,
                    category="pii",
                    message=(
                        f"Cell {cell.index}: email address '{email}' "
                        f"found in source. Verify it is not sensitive data."
                    ),
                ))

        # IP addresses
        for match in _RE_IP_ADDRESS.finditer(st):
            ip_count += 1
            findings.append(Finding(
                severity="info",
                cell_index=cell.index,
                category="pii",
                message=(
                    f"Cell {cell.index}: IP address '{match.group(0)}' "
                    f"found in source."
                ),
            ))

        # Credentials
        for match in _RE_CREDENTIAL.finditer(st):
            cred_count += 1
            findings.append(Finding(
                severity="error",
                cell_index=cell.index,
                category="pii",
                message=(
                    f"Cell {cell.index}: possible credential assignment "
                    f"detected (api_key, password, secret, token)."
                ),
            ))

        # AWS keys
        for match in _RE_AWS_KEY.finditer(st):
            aws_count += 1
            findings.append(Finding(
                severity="error",
                cell_index=cell.index,
                category="pii",
                message=(
                    f"Cell {cell.index}: AWS access key pattern "
                    f"'{match.group(0)}' detected -- potential credential leak."
                ),
            ))

        # SSH keys
        if _RE_SSH_KEY.search(st):
            ssh_count += 1
            findings.append(Finding(
                severity="error",
                cell_index=cell.index,
                category="pii",
                message=(
                    f"Cell {cell.index}: SSH private key detected -- "
                    f"potential credential leak."
                ),
            ))

    if not findings:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="pii",
            message="No PII concerns detected.",
        ))
        return {
            "status": "passed",
            "findings": findings,
            "details": "No PII detected.",
        }

    counts = []
    if email_count:
        counts.append(f"{email_count} email(s)")
    if ip_count:
        counts.append(f"{ip_count} IP address(es)")
    if cred_count:
        counts.append(f"{cred_count} credential(s)")
    if aws_count:
        counts.append(f"{aws_count} AWS key(s)")
    if ssh_count:
        counts.append(f"{ssh_count} SSH key(s)")

    details = "PII detected: " + ", ".join(counts) + "." if counts else "PII detected."
    return {
        "status": "flagged",
        "findings": findings,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Score and status
# ---------------------------------------------------------------------------


def _compute_score(
    versioning: dict[str, Any],
    separation: dict[str, Any],
    resources: dict[str, Any],
    env: dict[str, Any],
    pii: dict[str, Any],
) -> str:
    """Compute overall deployment readiness score.

    - ``"low"``: all applicable sub-checks pass, no errors.
    - ``"high"``: any PII errors or 3+ flagged sub-checks.
    - ``"moderate"``: mixed results.
    """
    flagged = 0
    has_pii_errors = False

    for result in (versioning, separation, resources, env, pii):
        if result["status"] == "flagged":
            flagged += 1

    # Check for PII errors specifically
    for f in pii.get("findings", []):
        if f.severity == "error":
            has_pii_errors = True
            break

    if has_pii_errors:
        return "high"
    if flagged == 0:
        return "low"
    if flagged >= 3:
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
    versioning: dict[str, Any],
    separation: dict[str, Any],
    resources: dict[str, Any],
    env: dict[str, Any],
    pii: dict[str, Any],
    findings: list[Finding],
    score: str,
    focus_areas: list[str],
) -> str:
    """Build narrative report text for PDF export."""
    lines: list[str] = [
        f"# Pass 6: Deployment Readiness -- {filename}",
        f"**Score**: {score.upper()}",
        "",
    ]

    if focus_areas:
        lines.append(f"**Focus areas**: {', '.join(focus_areas)}")
        lines.append("")

    # Artifact versioning
    lines.append("## Artifact Versioning")
    lines.append("")
    lines.append(f"  Status: **{versioning['status'].upper()}**")
    lines.append(f"  {versioning['details']}")
    lines.append("")

    # Inference/training separation
    lines.append("## Inference/Training Separation")
    lines.append("")
    lines.append(f"  Status: **{separation['status'].upper()}**")
    lines.append(f"  {separation['details']}")
    lines.append("")

    # Resource documentation
    lines.append("## Resource Documentation")
    lines.append("")
    lines.append(f"  Status: **{resources['status'].upper()}**")
    lines.append(f"  {resources['details']}")
    lines.append("")

    # Environment completeness
    lines.append("## Environment Completeness")
    lines.append("")
    lines.append(f"  Status: **{env['status'].upper()}**")
    lines.append(f"  {env['details']}")
    lines.append("")

    # PII scan
    lines.append("## PII & Data Privacy")
    lines.append("")
    lines.append(f"  Status: **{pii['status'].upper()}**")
    lines.append(f"  {pii['details']}")
    lines.append("")

    # Score justification
    lines.append("## Score Justification")
    lines.append("")
    sub_flagged = sum(
        1 for r in [versioning, separation, resources, env, pii]
        if r["status"] == "flagged"
    )
    errors = [f for f in findings if f.severity == "error"]
    lines.append(
        f"  {sub_flagged}/5 sub-check(s) flagged, "
        f"{len(errors)} PII error(s). "
        f"Overall deployment readiness risk: **{score.upper()}**."
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
