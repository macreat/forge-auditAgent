"""Data models for the notebook audit framework.

Defines the core dataclasses used throughout the audit pipeline:
:class:`Cell`, :class:`Notebook`, :class:`Finding`, :class:`PassResult`,
and :class:`AuditReport`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Cell:
    """A single cell within a Jupyter notebook.

    Attributes:
        index: Zero-based position within the notebook's cell array.
        cell_type: Either ``"code"`` or ``"markdown"``.
        source: Concatenated source lines of the cell.
        execution_count: The kernel execution count, or ``None`` if never run.
        outputs: List of output dicts as parsed from the notebook JSON.
    """

    index: int
    cell_type: str
    source: str
    execution_count: int | None
    outputs: list[dict]


@dataclass
class Notebook:
    """A parsed Jupyter notebook ready for audit passes.

    Attributes:
        filename: The original filename or URL stem.
        source: Origin indicator — ``"local"`` or ``"github"``.
        cells: Ordered list of parsed cells.
        metadata: The notebook-level metadata dict from the .ipynb file.
        valid: Whether the notebook passed structural validation.
        validation_errors: Human-readable error messages from validation.
    """

    filename: str
    source: str
    cells: list[Cell]
    metadata: dict
    valid: bool = True
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class Finding:
    """An individual finding produced by an audit pass.

    Attributes:
        severity: Severity level — ``"info"``, ``"warning"``, or ``"error"``.
        cell_index: Index of the related cell, or ``None`` if notebook-level.
        category: Short category label (e.g. ``"imports"``, ``"output_hygiene"``).
        message: Human-readable description of the finding.
    """

    severity: str
    cell_index: int | None
    category: str
    message: str


@dataclass
class PassResult:
    """Result of a single audit pass execution.

    Attributes:
        pass_name: Display name of the pass (e.g. ``"Structural Overview"``).
        pass_number: Ordinal position (1–6).
        score: Overall score — ``"low"``, ``"moderate"``, ``"high"``, or ``None``.
        status: Execution outcome — ``"passed"``, ``"flagged"``,
            ``"skipped"``, or ``"error"``.
        findings: List of findings produced by this pass.
        deliverable_text: Narrative summary suitable for PDF/JSON export.
    """

    pass_name: str
    pass_number: int
    score: str | None
    status: str
    findings: list[Finding]
    deliverable_text: str


@dataclass
class AuditReport:
    """Top-level report containing all audit pass results.

    Attributes:
        notebook_name: Name of the audited notebook.
        timestamp: ISO 8601 timestamp of when the audit was run.
        status: ``"complete"`` when all six passes ran, ``"partial"`` otherwise.
        focus_areas: List of focus area labels the user selected.
        passes: Ordered list of pass results.
    """

    notebook_name: str
    timestamp: str
    status: str
    focus_areas: list[str]
    passes: list[PassResult]
