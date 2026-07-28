"""Pass 2: Reproducibility Check — dependency declarations, random seeds,
hardcoded paths, and credentials.

Assesses whether the notebook can be reliably re-executed by checking:
dependency declaration with version pinning, global random seed configuration,
and presence of absolute paths or embedded credentials.
"""

from __future__ import annotations

import re
from typing import Any

from app.audit.models import Cell, Finding, Notebook, PassResult

_PASS_NAME = "Reproducibility Check"
_PASS_NUMBER = 2

# Regex patterns
_RE_PIP_INSTALL = re.compile(r"!pip\s+install\s+(.+)$", re.MULTILINE)
_RE_CONDA_INSTALL = re.compile(r"!conda\s+install\s+(.+)$", re.MULTILINE)
_RE_PINNED_VERSION = re.compile(r"[a-zA-Z0-9_.-]+==[\d.*]+")
_RE_PACKAGE_NAME = re.compile(r"[a-zA-Z0-9_.-]+")

_RE_RANDOM_SEEDS: dict[str, re.Pattern] = {
    "numpy": re.compile(r"np(?:\.random)?\.seed\s*\("),
    "torch": re.compile(r"torch\.manual_seed\s*\("),
    "random": re.compile(r"random\.seed\s*\("),
    "tensorflow": re.compile(r"tf\.random\.set_seed\s*\("),
}

_RE_HOME_PATH = re.compile(r"/home/\S+")
_RE_USERS_PATH = re.compile(r"/Users/\S+")
_RE_WIN_PATH = re.compile(r"[Cc]:\\(?:[^\\\s]+\\)*\S+")
_RE_CREDENTIAL = re.compile(
    r"(?:api[_-]?key|password|secret|token|auth[_-]?token)\s*=\s*['\"](.+?)['\"]",
    re.IGNORECASE,
)
_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def run(
    notebook: Notebook,
    focus_areas: list[str] | None = None,
) -> PassResult:
    """Execute Pass 2: Reproducibility Check.

    Scans all code cells for:
    - Dependency declarations (``!pip install``, ``!conda install``)
      with or without pinned versions.
    - Global random seed calls (numpy, torch, random, tensorflow).
    - Hardcoded absolute paths and embedded credentials.

    Args:
        notebook: The parsed notebook to analyse.
        focus_areas: If provided and ``"reproducibility"`` is not included,
            returns a skipped result.  Effectively unused in this pass since
            reproducibility is always relevant, but kept for API consistency.

    Returns:
        A :class:`PassResult` with status and score.
    """
    findings: list[Finding] = []

    dep_result = _check_dependencies(notebook)
    findings.extend(dep_result["findings"])

    seed_result = _check_random_seeds(notebook)
    findings.extend(seed_result["findings"])

    path_result = _check_hardcoded_paths(notebook)
    findings.extend(path_result["findings"])

    score = _compute_score(dep_result, seed_result, path_result)
    status = _compute_status(findings)

    deliverable = _build_deliverable(
        notebook.filename, dep_result, seed_result, path_result,
        findings, score, focus_areas or [],
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


def _check_dependencies(notebook: Notebook) -> dict[str, Any]:
    """Check dependency declarations and version pinning.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"`` | ``"error"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"pinned"``: bool
    """
    findings: list[Finding] = []
    installed_packages: list[dict[str, Any]] = []
    has_declaration = False
    all_pinned = True

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue

        # !pip install
        for match in _RE_PIP_INSTALL.finditer(cell.source):
            has_declaration = True
            pkgs_str = match.group(1).strip()
            pkgs = _RE_PACKAGE_NAME.findall(pkgs_str)
            has_pin = bool(_RE_PINNED_VERSION.search(pkgs_str))

            # Ignore common flags like -q, --quiet, -r
            meaningful = [p for p in pkgs if not p.startswith("-") and p not in ("install", "pip")]

            if not has_pin and meaningful:
                all_pinned = False
                for pkg in meaningful:
                    installed_packages.append({"package": pkg, "pinned": False, "cell": cell.index})

            if has_pin and meaningful:
                for pkg in meaningful:
                    installed_packages.append({"package": pkg, "pinned": True, "cell": cell.index})

        # !conda install
        for match in _RE_CONDA_INSTALL.finditer(cell.source):
            has_declaration = True
            pkgs_str = match.group(1).strip()
            pkgs = _RE_PACKAGE_NAME.findall(pkgs_str)
            has_pin = bool(_RE_PINNED_VERSION.search(pkgs_str))

            meaningful = [p for p in pkgs if not p.startswith("-") and p not in ("install", "conda")]

            if not has_pin and meaningful:
                all_pinned = False
                for pkg in meaningful:
                    installed_packages.append({"package": pkg, "pinned": False, "cell": cell.index})

            if has_pin and meaningful:
                for pkg in meaningful:
                    installed_packages.append({"package": pkg, "pinned": True, "cell": cell.index})

    if not has_declaration:
        findings.append(Finding(
            severity="error",
            cell_index=None,
            category="dependency",
            message=(
                "No dependency declarations found. Notebook does not declare "
                "dependencies via !pip install or !conda install."
            ),
        ))
        return {
            "status": "error",
            "findings": findings,
            "details": "No dependency mechanism detected.",
            "pinned": False,
        }

    if all_pinned:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="dependency",
            message=(
                f"Dependencies declared and pinned "
                f"({len(installed_packages)} package(s))."
            ),
        ))
        return {
            "status": "passed",
            "findings": findings,
            "details": f"Dependencies declared and pinned ({len(installed_packages)} packages).",
            "pinned": True,
        }

    # Mixed or all unpinned
    unpinned = [p for p in installed_packages if not p["pinned"]]
    findings.append(Finding(
        severity="warning",
        cell_index=None,
        category="dependency",
        message=(
            f"{len(unpinned)} package(s) installed without pinned versions: "
            f"{', '.join(p['package'] for p in unpinned[:10])}"
            f"{'...' if len(unpinned) > 10 else ''}."
        ),
    ))
    return {
        "status": "flagged",
        "findings": findings,
        "details": (
            f"Dependencies declared but {len(unpinned)}/"
            f"{len(installed_packages)} package(s) lack version pinning."
        ),
        "pinned": False,
    }


def _check_random_seeds(notebook: Notebook) -> dict[str, Any]:
    """Check for global random seed configuration.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"`` | ``"error"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    - ``"seeds_found"``: list of seed descriptions
    """
    findings: list[Finding] = []
    seeds_found: list[str] = []
    has_stochastic_import = False

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source

        # Check for stochastic library imports
        if re.search(r"\bimport (numpy|torch|random|tensorflow)\b", source) or \
           re.search(r"\bfrom (numpy|torch|tensorflow)\b", source):
            has_stochastic_import = True

        # Check seed calls
        for lib_name, pattern in _RE_RANDOM_SEEDS.items():
            if pattern.search(source):
                seeds_found.append(f"{lib_name} (cell {cell.index})")

    if seeds_found:
        findings.append(Finding(
            severity="info",
            cell_index=None,
            category="random_seed",
            message=f"Global seed(s) found: {', '.join(seeds_found)}.",
        ))
        return {
            "status": "passed",
            "findings": findings,
            "details": f"Seeds configured: {', '.join(seeds_found)}.",
            "seeds_found": seeds_found,
        }

    if has_stochastic_import:
        findings.append(Finding(
            severity="warning",
            cell_index=None,
            category="random_seed",
            message=(
                "Stochastic libraries are imported (numpy, torch, random, "
                "tensorflow) but no global random seed is set. Results may "
                "not be reproducible across runs."
            ),
        ))
        return {
            "status": "flagged",
            "findings": findings,
            "details": "Stochastic imports found but no seeds set.",
            "seeds_found": [],
        }

    # No stochastic imports at all
    return {
        "status": "passed",
        "findings": findings,
        "details": "No stochastic libraries detected.",
        "seeds_found": [],
    }


def _check_hardcoded_paths(notebook: Notebook) -> dict[str, Any]:
    """Scan code cells for hardcoded paths and credential patterns.

    Returns a dict with keys:
    - ``"status"``: ``"passed"`` | ``"flagged"``
    - ``"findings"``: list of Finding
    - ``"details"``: human-readable summary
    """
    findings: list[Finding] = []
    path_count = 0
    cred_count = 0

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        source = cell.source

        # Hardcoded paths
        for pattern, label in [
            (_RE_HOME_PATH, "/home/"),
            (_RE_USERS_PATH, "/Users/"),
            (_RE_WIN_PATH, "C:\\"),
        ]:
            matches = pattern.findall(source)
            for m in matches:
                path_count += 1
                findings.append(Finding(
                    severity="warning",
                    cell_index=cell.index,
                    category="hardcoded_path",
                    message=f"Cell {cell.index}: hardcoded path '{m}'.",
                ))

        # Credentials
        cred_matches = _RE_CREDENTIAL.findall(source)
        for _ in cred_matches:
            cred_count += 1
            findings.append(Finding(
                severity="error",
                cell_index=cell.index,
                category="credential",
                message=(
                    f"Cell {cell.index}: possible credential assignment "
                    f"detected (api_key, password, secret, token)."
                ),
            ))

        # Email addresses
        email_matches = _RE_EMAIL.findall(source)
        for em in email_matches:
            findings.append(Finding(
                severity="warning",
                cell_index=cell.index,
                category="credential",
                message=f"Cell {cell.index}: email address '{em}' found in source.",
            ))

    if path_count == 0 and cred_count == 0:
        return {
            "status": "passed",
            "findings": findings,
            "details": "No hardcoded paths or credentials detected.",
        }

    details_parts = []
    if path_count > 0:
        details_parts.append(f"{path_count} hardcoded path(s)")
    if cred_count > 0:
        details_parts.append(f"{cred_count} credential-like string(s)")
    return {
        "status": "flagged",
        "findings": findings,
        "details": "Found: " + "; ".join(details_parts) + ".",
    }


# ---------------------------------------------------------------------------
# Score and status
# ---------------------------------------------------------------------------


def _compute_score(
    dep: dict[str, Any],
    seed: dict[str, Any],
    path: dict[str, Any],
) -> str:
    """Compute overall reproducibility score.

    - ``"low"``: all sub-checks pass.
    - ``"high"``: all sub-checks fail or are critically flagged.
    - ``"moderate"``: mixed results.
    """
    statuses = [dep["status"], seed["status"], path["status"]]
    passed = sum(1 for s in statuses if s == "passed")
    critical = sum(1 for s in statuses if s == "error")

    if passed == 3:
        return "low"
    if critical == 3 or (critical >= 2 and passed == 0):
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
    dep: dict[str, Any],
    seed: dict[str, Any],
    path: dict[str, Any],
    findings: list[Finding],
    score: str,
    focus_areas: list[str],
) -> str:
    """Build narrative report text for PDF export."""
    lines: list[str] = [
        f"# Pass 2: Reproducibility Check — {filename}",
        f"**Score**: {score.upper()}",
        "",
    ]

    if focus_areas:
        lines.append(f"**Focus areas**: {', '.join(focus_areas)}")
        lines.append("")

    # Dependency declaration
    lines.append("## Dependency Declarations")
    lines.append("")
    lines.append(f"  Status: **{dep['status'].upper()}**")
    lines.append(f"  {dep['details']}")
    lines.append("")

    # Random seeds
    lines.append("## Random Seeds")
    lines.append("")
    lines.append(f"  Status: **{seed['status'].upper()}**")
    lines.append(f"  {seed['details']}")
    lines.append("")

    # Hardcoded paths
    lines.append("## Hardcoded Paths & Credentials")
    lines.append("")
    lines.append(f"  Status: **{path['status'].upper()}**")
    lines.append(f"  {path['details']}")
    lines.append("")

    # Score justification
    lines.append("## Score Justification")
    lines.append("")
    sub_passed = sum(
        1 for s in [dep["status"], seed["status"], path["status"]]
        if s == "passed"
    )
    sub_total = 3
    lines.append(
        f"  {sub_passed}/{sub_total} sub-checks passed. "
        f"Overall reproducibility risk: **{score.upper()}**."
    )
    lines.append("")

    # Findings detail
    if findings:
        lines.append("## Detailed Findings")
        lines.append("")
        for f in findings:
            cell_ref = f"Cell {f.cell_index}" if f.cell_index is not None else "Notebook"
            lines.append(f"  - [{f.severity}] [{cell_ref}] [{f.category}] {f.message}")
        lines.append("")

    return "\n".join(lines).strip()
