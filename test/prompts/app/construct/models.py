"""Construct pipeline data models.

Follows the return-invalid-not-raise convention from :mod:`app.audit.models`:
loaders and gates never raise on user-facing failures; they return objects
with ``valid=False`` and a descriptive ``validation_errors`` list instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nbformat import NotebookNode


@dataclass
class SourceDocument:
    """A source document loaded into the Construct pipeline.

    Attributes:
        filename: Sanitized display name of the document (plain basename,
            no path separators).
        source: Loader kind — one of ``"local"``, ``"github"``, ``"http"``,
            ``"drive"``, ``"kaggle"``.
        content: The document text, decoded as UTF-8.
        valid: Whether the load succeeded and passed all gates.
        validation_errors: Reasons for ``valid=False``; empty when valid.
    """

    filename: str
    source: str
    content: str
    valid: bool = True
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class ConstructSession:
    """Accumulated state of one construct run (load → scaffold → draft → save).

    Attributes:
        source: The loaded :class:`SourceDocument`, or ``None`` before load.
        scaffold: The validated nbformat v4 scaffold notebook, or ``None``.
        drafted: The drafted notebook after :func:`app.construct.writer.draft_sections`,
            or ``None`` if drafting failed the final gate.
        saved_path: Absolute path of the exported ``.ipynb``, or ``None``.
        errors: Run-level errors (draft section failures, export failures,
            gate failures). Never empty on failure.
    """

    source: SourceDocument | None = None
    scaffold: NotebookNode | None = None
    drafted: NotebookNode | None = None
    saved_path: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class ScaffoldResult:
    """Result of :func:`app.construct.scaffold.build_scaffold`.

    A failed scaffold (nbformat validation gate) returns ``valid=False``
    with the validator's messages; it never raises.
    """

    notebook: NotebookNode | None = None
    valid: bool = False
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class ExportResult:
    """Result of :func:`app.construct.export.save_notebook`.

    Attributes:
        saved_path: Absolute path of the written ``.ipynb`` (atomic write),
            or ``None`` on failure.
        py_path: Absolute path of the optional flattened ``.py`` export, or
            ``None`` when skipped or on failure.
        valid: Whether the export succeeded.
        errors: Reasons for ``valid=False``; empty when valid.
    """

    saved_path: str | None = None
    py_path: str | None = None
    valid: bool = False
    errors: list[str] = field(default_factory=list)
