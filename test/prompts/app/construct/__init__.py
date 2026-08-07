"""Notebook Construction Framework (Part I of NotebookBuildAudit).

Mirrors the :mod:`app.audit` package structure: models with
return-invalid-not-raise semantics, public-file loaders, an nbformat v4
scaffold with the eight canonical section headers, per-section LLM drafting
with strict output-format enforcement, and atomic export to the notebooks
directory that the Audit tab scans.

Modules:
    - :mod:`app.construct.models` — ``SourceDocument``, ``ConstructSession``,
      ``ScaffoldResult``, ``ExportResult``
    - :mod:`app.construct.loaders` — local / GitHub / generic HTTP / Google
      Drive / Kaggle loaders
    - :mod:`app.construct.scaffold` — nbformat v4 scaffold with canonical
      headers, env-pin cell, and reproducibility cell
    - :mod:`app.construct.prompts` — per-section drafting instructions
    - :mod:`app.construct.writer` — sequential drafting loop with retry-once
      and validation gates
    - :mod:`app.construct.export` — versioned, atomic notebook export
"""
