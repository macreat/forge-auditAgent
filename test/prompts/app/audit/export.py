"""Export utilities — JSON and PDF report generation.

Provides :func:`to_json` for structured data export and :func:`to_pdf`
for formatted document generation using ReportLab.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.audit.models import AuditReport, Finding, PassResult


def to_json(report: AuditReport, path: str) -> None:
    """Serialize an audit report to a JSON file.

    Produces a JSON object with ``"status"`` set to ``"complete"`` or
    ``"partial"`` at the top level, and a ``"passes"`` array containing
    each pass result with its findings.

    Args:
        report: The completed audit report.
        path: Filesystem path for the output ``.json`` file. Parent
            directories are created if they do not exist.
    """
    ensure_export_dir(path)

    data = {
        "notebook_name": report.notebook_name,
        "timestamp": report.timestamp,
        "status": report.status,
        "focus_areas": report.focus_areas,
        "passes": [_pass_to_dict(p) for p in report.passes],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _pass_to_dict(p: PassResult) -> dict:
    """Convert a PassResult to a JSON-serialisable dict."""
    return {
        "pass_name": p.pass_name,
        "pass_number": p.pass_number,
        "score": p.score,
        "status": p.status,
        "findings": [_finding_to_dict(f) for f in p.findings],
        "deliverable_text": p.deliverable_text,
    }


def _finding_to_dict(f: Finding) -> dict:
    """Convert a Finding to a JSON-serialisable dict."""
    return {
        "severity": f.severity,
        "cell_index": f.cell_index,
        "category": f.category,
        "message": f.message,
    }


def to_pdf(report: AuditReport, path: str) -> None:
    """Generate a formatted PDF report from audit results.

    Produces a multi-page PDF with:
    - A cover page showing notebook name, audit timestamp, and status.
    - One section per executed pass with a colour-coded score badge
      (green for low, orange for moderate, red for high).
    - A findings list within each pass section.
    - A final recommendations section aggregating high-severity items.

    Args:
        report: The completed audit report.
        path: Filesystem path for the output ``.pdf`` file. Parent
            directories are created if they do not exist.
    """
    ensure_export_dir(path)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        title=f"Audit Report - {report.notebook_name}",
    )

    styles = getSampleStyleSheet()
    story: list = []

    # ------------------------------------------------------------------
    # Cover page
    # ------------------------------------------------------------------
    story.append(Paragraph("Audit Report", styles["Title"]))
    story.append(Spacer(1, 6 * mm))
    story.append(
        Paragraph(
            f"<b>Notebook:</b> {report.notebook_name}", styles["Normal"]
        )
    )
    story.append(
        Paragraph(f"<b>Date:</b> {report.timestamp}", styles["Normal"])
    )
    story.append(
        Paragraph(
            f"<b>Status:</b> {report.status.upper()}", styles["Normal"]
        )
    )
    if report.focus_areas:
        story.append(
            Paragraph(
                f"<b>Focus Areas:</b> {', '.join(report.focus_areas)}",
                styles["Normal"],
            )
        )
    story.append(Spacer(1, 12 * mm))

    # ------------------------------------------------------------------
    # Colour map for score badges
    # ------------------------------------------------------------------
    _SCORE_COLORS = {
        "low": colors.HexColor("#4CAF50"),
        "moderate": colors.HexColor("#FF9800"),
        "high": colors.HexColor("#F44336"),
    }

    # ------------------------------------------------------------------
    # Per-pass sections
    # ------------------------------------------------------------------
    for p in report.passes:
        # Score badge HTML fragment
        score_fragment = ""
        if p.score:
            badge_color = _SCORE_COLORS.get(p.score.lower(), colors.grey)
            score_fragment = (
                f'<font color="{badge_color.hexval()}">'
                f"<b>[{p.score.upper()}]</b></font>"
            )

        status_label = p.status.upper()
        story.append(Spacer(1, 6 * mm))
        story.append(
            Paragraph(
                f"<b>Pass {p.pass_number}: {p.pass_name}</b> "
                f"{score_fragment} {status_label}",
                styles["Heading2"],
            )
        )
        story.append(Spacer(1, 3 * mm))

        if p.findings:
            for finding in p.findings:
                cell_ref = (
                    f"Cell {finding.cell_index}"
                    if finding.cell_index is not None
                    else "Notebook"
                )
                severity_tag = finding.severity.upper()
                story.append(
                    Paragraph(
                        f"- <b>[{severity_tag}]</b> [{cell_ref}] "
                        f"[{finding.category}] {finding.message}",
                        styles["Normal"],
                    )
                )
                story.append(Spacer(1, 1 * mm))
        else:
            story.append(Paragraph("No findings.", styles["Normal"]))

        # Deliverable excerpt
        story.append(Spacer(1, 3 * mm))
        excerpt = p.deliverable_text[:300]
        if len(p.deliverable_text) > 300:
            excerpt += " ..."
        story.append(
            Paragraph(f"<i>Deliverable:</i> {excerpt}", styles["Normal"])
        )

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph("Recommendations", styles["Heading1"]))
    story.append(Spacer(1, 3 * mm))

    high_severity: list[Finding] = [
        f
        for p in report.passes
        for f in p.findings
        if f.severity == "error"
    ]
    if high_severity:
        story.append(
            Paragraph("High-severity items to address:", styles["Normal"])
        )
        for f in high_severity:
            story.append(
                Paragraph(
                    f"- [{f.category}] {f.message}",
                    styles["Normal"],
                )
            )
    else:
        story.append(
            Paragraph(
                "No high-severity recommendations.", styles["Normal"]
            )
        )

    doc.build(story)


def ensure_export_dir(path: str) -> None:
    """Create the parent directory for an export file if it does not exist.

    Args:
        path: Filesystem path to an export file whose parent directory
            should be created.
    """
    parent = Path(path).parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
