"""Notebook file loader — local filesystem and GitHub raw URL.

Provides :func:`load_notebook` for local ``.ipynb`` files and
:func:`load_from_github` for public GitHub raw URLs. Both return a
:class:`~app.audit.models.Notebook` instance with structural validation
applied; invalid notebooks are returned with ``valid=False`` and a list of
validation errors rather than raising exceptions.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.audit.models import Cell, Notebook


def load_notebook(path: str) -> Notebook:
    """Load and validate a Jupyter notebook from a local file.

    Args:
        path: Absolute or relative filesystem path to a ``.ipynb`` file.

    Returns:
        A :class:`Notebook` instance. If the file cannot be read or parsed,
        ``valid`` is ``False`` and ``validation_errors`` contain the reasons.
    """
    filename = Path(path).name

    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return Notebook(
            filename=filename,
            source="local",
            cells=[],
            metadata={},
            valid=False,
            validation_errors=[f"File not found: {path}"],
        )
    except OSError as exc:
        return Notebook(
            filename=filename,
            source="local",
            cells=[],
            metadata={},
            valid=False,
            validation_errors=[f"Cannot read file: {exc}"],
        )

    return _parse_notebook(raw, filename, source="local")


def load_from_github(url: str, filename: str | None = None) -> Notebook:
    """Fetch and validate a Jupyter notebook from a public GitHub raw URL.

    Args:
        url: Full raw.githubusercontent.com URL pointing to a ``.ipynb`` file.
        filename: Optional override for the notebook name. If omitted, the
            last path segment of the URL is used.

    Returns:
        A :class:`Notebook` instance. Network errors, non-200 responses, and
        parse failures result in ``valid=False`` with descriptive errors.
    """
    name = filename or url.rstrip("/").split("/")[-1]

    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.TimeoutException:
        return Notebook(
            filename=name,
            source="github",
            cells=[],
            metadata={},
            valid=False,
            validation_errors=[f"Request timed out: {url}"],
        )
    except httpx.HTTPStatusError as exc:
        return Notebook(
            filename=name,
            source="github",
            cells=[],
            metadata={},
            valid=False,
            validation_errors=[
                f"HTTP {exc.response.status_code} fetching {url}"
            ],
        )
    except httpx.RequestError as exc:
        return Notebook(
            filename=name,
            source="github",
            cells=[],
            metadata={},
            valid=False,
            validation_errors=[f"Network error fetching {url}: {exc}"],
        )

    return _parse_notebook(resp.content, name, source="github")


def _parse_notebook(raw: bytes, filename: str, source: str) -> Notebook:
    """Parse raw JSON bytes into a validated Notebook.

    Args:
        raw: UTF-8 encoded JSON content of a .ipynb file.
        filename: Display name for the notebook.
        source: ``"local"`` or ``"github"``.

    Returns:
        A :class:`Notebook` with structural validation applied.
    """
    errors: list[str] = []

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return Notebook(
            filename=filename,
            source=source,
            cells=[],
            metadata={},
            valid=False,
            validation_errors=[f"Malformed JSON: {exc}"],
        )

    # Validate top-level structure
    if not isinstance(data, dict):
        return Notebook(
            filename=filename,
            source=source,
            cells=[],
            metadata={},
            valid=False,
            validation_errors=[f"Top-level value must be a JSON object, got {type(data).__name__}"],
        )

    if "cells" not in data:
        errors.append('Missing required key "cells"')
    elif not isinstance(data["cells"], list):
        errors.append(f'"cells" must be an array, got {type(data["cells"]).__name__}')

    if "metadata" not in data:
        errors.append('Missing required key "metadata"')
    elif not isinstance(data["metadata"], dict):
        errors.append(f'"metadata" must be an object, got {type(data["metadata"]).__name__}')

    if errors:
        return Notebook(
            filename=filename,
            source=source,
            cells=[],
            metadata={},
            valid=False,
            validation_errors=errors,
        )

    # Parse cells
    cells: list[Cell] = []
    cell_array: list = data["cells"]

    for i, raw_cell in enumerate(cell_array):
        if not isinstance(raw_cell, dict):
            errors.append(f"Cell at index {i} is not an object")
            continue

        cell_type = raw_cell.get("cell_type")
        if cell_type not in ("code", "markdown"):
            errors.append(
                f"Cell at index {i}: 'cell_type' must be 'code' or 'markdown', "
                f"got {cell_type!r}"
            )
            continue

        if "source" not in raw_cell:
            errors.append(f"Cell at index {i}: missing required field 'source'")
            continue

        source_lines = raw_cell["source"]
        if isinstance(source_lines, list):
            source_text = "".join(source_lines)
        elif isinstance(source_lines, str):
            source_text = source_lines
        else:
            errors.append(
                f"Cell at index {i}: 'source' must be a string or list of "
                f"strings, got {type(source_lines).__name__}"
            )
            continue

        exec_count = raw_cell.get("execution_count")
        outputs = raw_cell.get("outputs", [])

        cells.append(
            Cell(
                index=i,
                cell_type=cell_type,
                source=source_text,
                execution_count=exec_count,
                outputs=outputs if isinstance(outputs, list) else [],
            )
        )

    valid = len(errors) == 0

    return Notebook(
        filename=filename,
        source=source,
        cells=cells,
        metadata=data.get("metadata", {}),
        valid=valid,
        validation_errors=errors,
    )
