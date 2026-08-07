"""Per-section LLM drafting loop with strict output-format enforcement.

Implements Part I / Phase 2 of the Construction Framework: sections are
drafted one at a time, in canonical order, through an
:class:`app.api.utils.LLMProvider`. Each section is validated before
acceptance (strict ``===MARKDOWN===``/``===CODE===`` grammar, ``ast.parse``
per code block) and retried at most once on any failure — a validation
failure or a :class:`app.api.utils.ProviderError` counts equally. A section
that fails twice is recorded as a draft error and does not block the
remaining sections. The assembled notebook passes ``nbformat.validate`` and
``ast.parse`` over every code cell before being accepted.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field

import nbformat
from nbformat import NotebookNode

from app.api.utils import LLMProvider, ProviderError
from app.construct.models import ConstructSession, SourceDocument
from app.construct.prompts import section_instructions
from app.construct.scaffold import CANONICAL_HEADERS, _pin_cell

_MARKERS = ("===MARKDOWN===", "===CODE===")


@dataclass
class SectionParse:
    """Result of :func:`parse_section_output`.

    Attributes:
        blocks: Parsed blocks as ``(kind, content)`` pairs where ``kind`` is
            ``"markdown"`` or ``"code"``, in output order.
        errors: Format violations; empty when the output conforms.
    """

    blocks: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _marker_of(line: str) -> str | None:
    """Return the marker name when ``line`` is exactly a marker (ignoring
    surrounding whitespace), else ``None``."""
    stripped = line.strip()
    if stripped in _MARKERS:
        return stripped
    return None


def parse_section_output(text: str) -> SectionParse:
    """Parse provider output in the strict per-section format.

    Grammar (line-based):

    - A section is one or more blocks, each introduced by a marker line
      (``===MARKDOWN===`` or ``===CODE===``) alone on its own line.
    - Every section output MUST contain at least one ``===MARKDOWN===``
      block; ``===CODE===`` blocks are optional.
    - The line after a marker begins that block's content; the block ends at
      the next marker line (or at the end of the output).
    - Content lines are verbatim; a content line equal to a marker escaped
      with one leading backslash (``\\===CODE===``) is kept as literal
      content with exactly one leading backslash removed.

    Off-format output returns a :class:`SectionParse` with non-empty
    ``errors`` (the retry rule applies).
    """
    parsed = SectionParse()
    current_kind: str | None = None
    current_lines: list[str] = []
    saw_markdown = False
    leading_content: list[str] = []

    for line in text.splitlines():
        marker = _marker_of(line)
        if marker is not None:
            if current_kind is None and leading_content:
                parsed.errors.append(
                    "Content before the first marker line is not allowed: "
                    + repr("\n".join(leading_content)[:40])
                )
            if current_kind is not None:
                parsed.blocks.append((current_kind, "\n".join(current_lines)))
            current_kind = "markdown" if marker == "===MARKDOWN===" else "code"
            current_lines = []
            if marker == "===MARKDOWN===":
                saw_markdown = True
        elif line.startswith("\\") and _marker_of(line[1:]) is not None:
            # Escaped marker line -> literal content (drop exactly one
            # leading backslash).
            if current_kind is None:
                leading_content.append(line)
            else:
                current_lines.append(line[1:])
        else:
            if current_kind is None:
                leading_content.append(line)
            else:
                current_lines.append(line)

    if current_kind is not None:
        parsed.blocks.append((current_kind, "\n".join(current_lines)))
    elif not leading_content and not text.strip():
        parsed.errors.append(
            "Section output is empty; expected at least one "
            "===MARKDOWN=== block"
        )
    elif not saw_markdown:
        parsed.errors.append(
            "No ===MARKDOWN=== marker found in section output"
        )

    if not saw_markdown:
        parsed.errors.append(
            "Section output must contain at least one ===MARKDOWN=== block"
        )

    return parsed


def validate_code_blocks(parsed: SectionParse) -> str | None:
    """Run ``ast.parse`` over every code block. Returns an error string or
    ``None`` when all code blocks are syntactically valid."""
    for kind, content in parsed.blocks:
        if kind == "code":
            try:
                ast.parse(content)
            except SyntaxError as exc:
                return f"Code block failed ast.parse: {exc}"
    return None


def _section_end_index(cells: list[NotebookNode], header: str) -> int:
    """Index one past the last cell that belongs to ``header``'s section
    (the header cell plus its Phase 1 pin cell, when present)."""
    end = 0
    for index, cell in enumerate(cells):
        source = getattr(cell, "source", "")
        if isinstance(source, list):
            source = "".join(source)
        if cell.cell_type == "markdown" and source.strip() == f"## {header}":
            end = index + 1
            # The pin cell directly follows the header in the scaffold.
            pin = _pin_cell(header)
            if pin is not None and index + 1 < len(cells):
                end = index + 2
            break
    return end


async def _draft_section(
    header: str,
    source: SourceDocument,
    provider: LLMProvider,
) -> tuple[list[tuple[str, str]] | None, str | None]:
    """Draft one section with retry-once. Returns ``(blocks, error)`` —
    exactly one of the two is ``None``."""
    instructions = section_instructions(header)
    last_error: str | None = None
    for _attempt in (1, 2):
        try:
            text = await provider.draft_section(
                header, instructions, source.content
            )
        except ProviderError as exc:
            last_error = (
                f"Section {header!r}: provider error: {exc}"
            )
            continue  # retry once
        parsed = parse_section_output(text)
        if parsed.errors:
            last_error = (
                f"Section {header!r}: output failed validation: "
                + "; ".join(parsed.errors)
            )
            continue  # retry once
        code_error = validate_code_blocks(parsed)
        if code_error:
            last_error = f"Section {header!r}: {code_error}"
            continue  # retry once
        return parsed.blocks, None
    return None, last_error


def _final_gates(notebook: NotebookNode) -> list[str]:
    """Post-validation gates on the assembled notebook: ``nbformat.validate``
    and ``ast.parse`` over every code cell. Returns a list of errors."""
    errors: list[str] = []
    try:
        nbformat.validate(notebook)
    except nbformat.ValidationError as exc:
        errors.append(f"Drafted notebook failed nbformat validation: {exc}")
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "code":
            continue
        source = cell.source if isinstance(cell.source, str) else "".join(cell.source)
        try:
            ast.parse(source)
        except SyntaxError as exc:
            errors.append(f"Code cell {index} failed ast.parse: {exc}")
    return errors


async def draft_sections(
    scaffold: NotebookNode | None,
    source: SourceDocument | None,
    provider: LLMProvider,
    progress_cb=None,
) -> ConstructSession:
    """Draft every canonical section sequentially into a new notebook.

    Args:
        scaffold: Validated scaffold from :func:`app.construct.scaffold.build_scaffold`.
        source: The loaded source document (context for the LLM only).
        provider: The active :class:`LLMProvider`.
        progress_cb: Optional ``async``/sync callback invoked once per
            section after its attempt cycle resolves, with
            ``(done, total, header, message)`` where ``message`` is ``"ok"``
            or ``"failed: ..."``. Callback exceptions are swallowed so a UI
            callback can never abort drafting.

    Returns:
        A :class:`ConstructSession`. Failed sections are recorded in
        ``errors`` and drafting continues. The drafted notebook is set only
        when the final gates pass.
    """
    session = ConstructSession(source=source, scaffold=scaffold)
    if scaffold is None:
        session.errors.append("No scaffold available for drafting")
        return session
    if source is None or not source.valid:
        session.errors.append(
            "No valid source document available for drafting"
        )
        return session

    notebook = copy.deepcopy(scaffold)
    cells = list(notebook.cells)

    for done, header in enumerate(CANONICAL_HEADERS, start=1):
        end = _section_end_index(cells, header)
        if end == 0:
            session.errors.append(
                f"Scaffold missing placeholder for section {header!r}; "
                "section skipped"
            )
        blocks, error = await _draft_section(header, source, provider)
        if error is None and end > 0:
            drafted_cells: list[NotebookNode] = []
            for kind, content in blocks or []:
                if kind == "markdown":
                    drafted_cells.append(nbformat.v4.new_markdown_cell(content))
                else:
                    drafted_cells.append(nbformat.v4.new_code_cell(content))
            cells[end:end] = drafted_cells
            message = "ok"
        else:
            if error is not None:
                session.errors.append(error)
            message = f"failed: {error or 'no placeholder'}"

        if progress_cb is not None:
            try:
                result = progress_cb(done, len(CANONICAL_HEADERS), header, message)
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                # A UI progress callback must never abort drafting.
                pass

    notebook.cells = cells

    # A run where every section failed produces no drafted notebook.
    if len(session.errors) >= len(CANONICAL_HEADERS):
        return session

    gate_errors = _final_gates(notebook)
    if gate_errors:
        session.errors.extend(gate_errors)
        return session

    session.drafted = notebook
    return session
