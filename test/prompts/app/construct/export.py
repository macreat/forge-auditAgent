"""Notebook export: versioned, atomic save into the notebooks directory.

The exporter writes the constructed ``.ipynb`` into
:func:`app.config.paths.defaultNotebooksDir` — the same directory the Audit
tab's Scan DB scans — closing the construct → audit loop. Names are
collision-free: ``name.ipynb`` first, then ``name-v2.ipynb``, ``name-v3.ipynb``,
etc. Writes are atomic (temp file in the same directory + ``os.replace``).

Optionally exports a flattened ``.py`` script (code cells concatenated with
comments) alongside the ``.ipynb``. Note on the Audit Scan DB: the scanner's
extension whitelist is ``.ipynb``/``.py``/``.md``/``.txt``, so an opted-in
``.py`` export will appear in the Scan DB listing. The audit loader itself
only parses ``.ipynb`` JSON, so loading the flattened ``.py`` through the
audit path is not supported — the two files are separate artifacts.

The notebooks directory is ``defaultNotebooksDir()`` (dev: project-local
``notebooks/``; deployed: ``~/.test-prompts/notebooks/``); pass
``notebooks_dir`` to override (used by tests/probes).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import nbformat
from nbformat import NotebookNode

from app.config.paths import defaultNotebooksDir
from app.construct.loaders import sanitize_filename
from app.construct.models import ExportResult


def flatten_to_py(notebook: NotebookNode) -> str:
    """Concatenate the notebook's code cells into a flat ``.py`` script.

    Each code cell is prefixed with a comment marker; markdown cells are
    skipped. The result is comment-safe (no ``!``-magic lines) and valid
    Python when every code cell is valid.
    """
    parts: list[str] = [
        "# Flattened Python export generated from a Construct notebook."
    ]
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "code":
            continue
        source = cell.source if isinstance(cell.source, str) else "".join(cell.source)
        source = source.rstrip("\n")
        parts.append(f"\n# --- code cell {index} ---")
        if source:
            parts.append(source)
    return "\n".join(parts) + "\n"


def _base_stem(base_name: str) -> str | None:
    """Sanitize the export base name (a SourceDocument filename) to its
    extension-free stem. Returns ``None`` when unsafe."""
    if not base_name or "/" in base_name or "\\" in base_name:
        return None
    if base_name in (".", ".."):
        return None
    stem = Path(base_name).stem
    return sanitize_filename(stem)


def _next_available(directory: Path, filename: str) -> Path:
    """Collision-free path: ``filename``, then ``name-v2.ext``, etc."""
    target = directory / filename
    if not target.exists():
        return target
    name, ext = os.path.splitext(filename)
    for version in range(2, 10000):
        candidate = directory / f"{name}-v{version}{ext}"
        if not candidate.exists():
            return candidate
    raise OSError(
        f"could not find a free versioned filename for {filename!r}"
    )


def _atomic_write(path: Path, text: str) -> str | None:
    """Write ``text`` to ``path`` atomically: a temp file in the same
    directory, fsync'd, then ``os.replace``. Returns an error string or
    ``None`` on success."""
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        return None
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        return f"Cannot write {path.name}: {exc}"


def save_notebook(
    notebook: NotebookNode,
    base_name: str,
    export_py: bool = False,
    notebooks_dir: str | None = None,
) -> ExportResult:
    """Save a validated notebook to the notebooks directory.

    Args:
        notebook: A validated nbformat v4 notebook (the drafted notebook).
        base_name: Base name for the export, typically
            ``SourceDocument.filename`` (e.g. ``"notes.md"``). The extension
            is stripped; the resulting stem is sanitized.
        export_py: When true, also write a flattened ``.py`` script
            alongside the ``.ipynb``.
        notebooks_dir: Target directory; defaults to
            :func:`app.config.paths.defaultNotebooksDir`.

    Returns:
        An :class:`ExportResult`. The ``.ipynb`` is written atomically with a
        collision-free versioned name; failures (directory creation, write
        errors, invalid notebook, unsafe name) return ``valid=False`` with
        descriptive errors.
    """
    if notebook is None:
        return ExportResult(errors=["No notebook provided for export"])
    try:
        nbformat.validate(notebook)
    except nbformat.ValidationError as exc:
        return ExportResult(
            errors=[f"Notebook failed nbformat validation: {exc}"]
        )

    stem = _base_stem(base_name)
    if stem is None:
        return ExportResult(
            errors=[f"Unsafe export base name: {base_name!r}"]
        )

    target_dir = Path(notebooks_dir) if notebooks_dir else Path(defaultNotebooksDir())
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ExportResult(
            errors=[
                f"Cannot create notebooks directory {target_dir}: {exc}"
            ]
        )

    try:
        nb_path = _next_available(target_dir, f"{stem}.ipynb")
    except OSError as exc:
        return ExportResult(errors=[str(exc)])

    nb_json = nbformat.writes(notebook, version=4)
    write_error = _atomic_write(nb_path, nb_json)
    if write_error:
        return ExportResult(errors=[write_error])

    result = ExportResult(saved_path=str(nb_path), valid=True)

    if export_py:
        try:
            py_path = _next_available(target_dir, f"{stem}.py")
        except OSError as exc:
            result.valid = False
            result.errors.append(str(exc))
            return result
        py_error = _atomic_write(py_path, flatten_to_py(notebook))
        if py_error:
            result.valid = False
            result.errors.append(py_error)
        else:
            result.py_path = str(py_path)

    return result
