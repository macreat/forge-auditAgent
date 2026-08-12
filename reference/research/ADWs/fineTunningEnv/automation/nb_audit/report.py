"""Final audit report generation (spec §25, §22; REQ-012, REQ-014).

Converts an :class:`~nb_audit.controller.AuditOutcome` into the two terminal
artifacts of a run:

* ``audit.json`` — the machine-readable audit document: the initial severity>8
  findings, the iteration history, the recurring findings, the §22
  final-verification checklist, and the summary line
  ``Unresolved findings > 8: N / Status: PASS|FAILED``.
* ``report.md`` — the human-readable §25 report (FINAL STATUS + checklist +
  iteration history).

Rendering is split into two pure stages so the ``report`` CLI subcommand can
re-emit ``report.md`` from a *persisted* ``audit.json`` without reconstructing
live :class:`Finding` objects:

* :func:`build_report_documents` — ``AuditOutcome`` → :class:`ReportDocuments`.
* :func:`render_markdown` — a persisted ``audit.json`` dict → ``report.md`` text.

Both stages are deterministic and LLM-free. The §22 checklist's mechanical
items (0 unresolved >8, no previous >8 unresolved, no new >8 regression) are
derived directly from the outcome; the semantic items (code/docs agree, protocol
agrees, metrics match, plots match, artifacts correspond, conclusions supported,
reproducibility/QA) are derived from their finding categories: an item passes
only when no unresolved severity>threshold finding in its categories remains.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from nb_audit.controller import AuditOutcome, IterationRecord
from nb_audit.models import Finding, Status

# A finding does not block PASS when its status is terminal-non-blocking
# (resolved, or user-accepted wont_fix) — mirrors the controller's predicate.
_NON_BLOCKING = (Status.RESOLVED, Status.WONT_FIX)

# Still-open lifecycle states (anything that is not resolved/wont_fix).
_OPEN_STATUSES = (Status.UNRESOLVED, Status.PATCHED, Status.RECURRING)

# Semantic §22 checklist items mapped to the finding categories they cover.
_CHECKLIST_SEMANTIC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("code and documentation agree", ("documentation", "markdown", "code")),
    (
        "experimental protocol agrees with implementation",
        ("experimental_validity", "protocol", "splits", "preprocessing"),
    ),
    ("metrics match definitions", ("metrics",)),
    ("plots/tables match metrics", ("plots", "tables")),
    ("artifacts correspond to experiment", ("artifacts",)),
    ("conclusions are supported", ("conclusions",)),
    ("reproducibility/QA checks pass", ("reproducibility", "qa", "execution")),
)


# --------------------------------------------------------------------------- #
# Finding selection helpers
# --------------------------------------------------------------------------- #
def blocking_findings(
    findings: Iterable[Finding], threshold: int = 8
) -> list[Finding]:
    """Findings that block PASS: severity > threshold and not terminal."""
    return [
        f
        for f in findings
        if f.severity > threshold and f.status not in _NON_BLOCKING
    ]


def _all_findings(outcome: AuditOutcome) -> list[Finding]:
    """Flatten every iteration's findings (deduplicated by id)."""
    seen: dict[str, Finding] = {}
    for iteration in outcome.iterations:
        for finding in iteration.findings:
            seen[finding.id] = finding
    return list(seen.values())


def initial_findings_gt8(
    outcome: AuditOutcome, threshold: int = 8
) -> list[Finding]:
    """The severity>threshold findings from the FIRST audit (before any patch).

    Their status has since been transitioned by the controller (e.g. a patched
    signature that disappeared becomes ``resolved``), so the ``Result`` field of
    each initial finding reflects its final disposition.
    """
    if not outcome.iterations:
        return []
    return [
        f for f in outcome.iterations[0].findings if f.severity > threshold
    ]


def recurring_findings(outcome: AuditOutcome) -> list[Finding]:
    """Findings whose root cause survived a patch (deduplicated by signature).

    Collects both the regression layer's ``recurring`` markers (a signature
    present before AND still unresolved now) and any finding the controller
    transitioned to ``recurring`` via its lifecycle. Keeps the latest per
    signature.
    """
    seen: dict[str, Finding] = {}
    for iteration in outcome.iterations:
        for finding in iteration.recurring:
            seen[finding.signature] = finding
        for finding in iteration.findings:
            if finding.status is Status.RECURRING:
                seen[finding.signature] = finding
    return list(seen.values())


# --------------------------------------------------------------------------- #
# Checklist (spec §22 Final Verification)
# --------------------------------------------------------------------------- #
def build_checklist(outcome: AuditOutcome, threshold: int = 8) -> list[dict]:
    """Build the §22 final-verification checklist with computed pass/fail.

    The first three items are the four-gate mechanical checks; the remaining
    seven are semantic-consistency checks evaluated from their finding
    categories (an item passes when no unresolved severity>threshold finding in
    its categories remains).
    """
    final = outcome.final_findings
    blocking = blocking_findings(final, threshold)
    history = _all_findings(outcome)

    items: list[dict] = [
        {"label": "0 unresolved findings > 8", "passed": not blocking},
        {
            "label": "no previous >8 issue remains unresolved",
            "passed": not blocking_findings(history, threshold),
        },
        {
            "label": "no new >8 regression",
            "passed": not any(
                f.regression and f.severity > threshold for f in history
            ),
        },
    ]
    for label, categories in _CHECKLIST_SEMANTIC:
        offending = [f for f in blocking if f.category in categories]
        items.append({"label": label, "passed": not offending})
    return items


# --------------------------------------------------------------------------- #
# Summary line
# --------------------------------------------------------------------------- #
def summary_line(unresolved_count: int, status: str) -> str:
    """The terminal summary line required by REQ-012 / §25."""
    return f"Unresolved findings > 8: {unresolved_count} / Status: {status}"


# --------------------------------------------------------------------------- #
# audit.json document
# --------------------------------------------------------------------------- #
def build_audit_json(outcome: AuditOutcome, threshold: int = 8) -> dict:
    """Serialize ``outcome`` into the canonical ``audit.json`` document."""
    blocking = blocking_findings(outcome.final_findings, threshold)
    unresolved_count = len(blocking)
    return {
        "status": outcome.status,
        "severity_threshold": threshold,
        "max_iterations": outcome.max_iterations,
        "reason": outcome.reason,
        "summary": summary_line(unresolved_count, outcome.status),
        "unresolved_gt8": unresolved_count,
        "initial_findings_gt8": [
            f.to_raw() for f in initial_findings_gt8(outcome, threshold)
        ],
        "recurring_findings": [
            f.to_raw() for f in recurring_findings(outcome)
        ],
        "iteration_history": [it.to_raw() for it in outcome.iterations],
        "final_findings": [f.to_raw() for f in outcome.final_findings],
        "checklist": build_checklist(outcome, threshold),
    }


# --------------------------------------------------------------------------- #
# report.md rendering (pure, over the audit.json document)
# --------------------------------------------------------------------------- #
def _render_finding_md(finding: Mapping[str, Any]) -> list[str]:
    location = finding.get("location") or {}
    cell = str(location.get("cell") or "")
    line = location.get("line")
    where = cell if line is None else f"{cell}:{line}"
    return [
        f"### {finding.get('id', '')}",
        "",
        f"- Severity: {finding.get('severity', '')}",
        f"- Classification: {finding.get('classification', '')}",
        f"- Location: {where or '-'}",
        f"- Root cause: {finding.get('root_cause', '') or '-'}",
        f"- Patch: {finding.get('correction', '') or '(none)'}",
        f"- Result: {finding.get('status', '')}",
        "",
    ]


def _render_iteration_md(iteration: Mapping[str, Any]) -> list[str]:
    findings = iteration.get("findings") or []
    if findings:
        ids = ", ".join(
            f"{f.get('id')} ({f.get('severity')}, {f.get('category')})"
            for f in findings
        )
    else:
        ids = "(none)"
    corrections = iteration.get("corrections") or {}
    patches = ", ".join(f"{k}: {v}" for k, v in corrections.items()) or "(none)"
    regressions = iteration.get("regressions") or []
    regressions_text = ", ".join(regressions) if regressions else "(none)"
    result = (
        f"exec={iteration.get('exec_status', '')}, "
        f"qa={iteration.get('qa_status', '')}"
    )
    return [
        f"### Iteration {iteration.get('iteration', '')}",
        "",
        f"- Findings: {ids}",
        f"- Patches: {patches}",
        f"- Regressions: {regressions_text}",
        f"- Result: {result}",
        "",
    ]


def render_markdown(doc: Mapping[str, Any]) -> str:
    """Render the §25 ``report.md`` from a persisted ``audit.json`` document."""
    lines: list[str] = ["# Final Audit", ""]

    lines.append("## Initial Findings > 8")
    lines.append("")
    initial = doc.get("initial_findings_gt8") or []
    if not initial:
        lines.append("(none)")
        lines.append("")
    for finding in initial:
        lines.extend(_render_finding_md(finding))

    lines.append("## Iteration History")
    lines.append("")
    for iteration in doc.get("iteration_history") or []:
        lines.extend(_render_iteration_md(iteration))

    lines.append("## Recurring Issues")
    lines.append("")
    recurring = doc.get("recurring_findings") or []
    if not recurring:
        lines.append("(none)")
        lines.append("")
    for finding in recurring:
        lines.extend(_render_finding_md(finding))

    lines.append("## Final Verification")
    lines.append("")
    for item in doc.get("checklist") or []:
        mark = "[x]" if item.get("passed") else "[ ]"
        lines.append(f"- {mark} {item.get('label', '')}")
    lines.append("")

    lines.append("## FINAL STATUS")
    lines.append("")
    lines.append(
        doc.get("summary")
        or summary_line(doc.get("unresolved_gt8", 0), doc.get("status", ""))
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Documents + filesystem
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReportDocuments:
    """The two terminal artifacts of a run (audit.json dict + report.md text)."""

    audit_json: dict
    markdown: str


def build_report_documents(
    outcome: AuditOutcome, threshold: int = 8
) -> ReportDocuments:
    """Build both terminal artifacts from an :class:`AuditOutcome`."""
    audit_json = build_audit_json(outcome, threshold)
    return ReportDocuments(
        audit_json=audit_json,
        markdown=render_markdown(audit_json),
    )


def write_report_documents(
    docs: ReportDocuments, run_dir: str | Path
) -> tuple[Path, Path]:
    """Write ``audit.json`` and ``report.md`` into ``run_dir``. Returns paths."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "audit.json"
    md_path = run_dir / "report.md"
    json_path.write_text(
        json.dumps(docs.audit_json, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(docs.markdown, encoding="utf-8")
    return json_path, md_path


def write_report(
    outcome: AuditOutcome, run_dir: str | Path, threshold: int = 8
) -> tuple[Path, Path]:
    """Convenience: build documents from ``outcome`` and write them to ``run_dir``."""
    return write_report_documents(
        build_report_documents(outcome, threshold), run_dir
    )


def load_audit_json(run_dir: str | Path) -> dict:
    """Load a persisted ``audit.json`` from a run directory (fail-closed).

    Raises :class:`FileNotFoundError` with a clear message when the document is
    missing, so the ``report`` CLI can exit non-zero on a missing run.
    """
    run_dir = Path(run_dir)
    path = run_dir / "audit.json"
    if not path.exists():
        raise FileNotFoundError(
            f"audit.json not found in run directory: {run_dir}"
        )
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
