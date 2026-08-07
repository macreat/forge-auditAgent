"""Notebook scaffold: build the canonical nbformat v4 skeleton.

Implements Part I / Phase 1 of the Construction Framework
(``reference/docs/mds/NotebookBuildAudit.md``):

- Eight canonical section headers as markdown cells, in canonical order.
- An environment-pin code cell placed in the "Environment & Dependencies"
  section (pin the execution environment upfront via requirements.txt,
  conda.yaml, or pyproject.toml).
- A reproducibility code cell placed in the "Configuration & Global
  Parameters" section (random seeds, deterministic flags, device config).

The scaffold is generic: the source document is never mapped into the
skeleton structure — it is attached as LLM context only. Every scaffold
passes through ``nbformat.validate``; a failing scaffold returns a defined
invalid result (``valid=False`` + ``validation_errors``) and never raises.
"""

from __future__ import annotations

import nbformat
from nbformat import NotebookNode

from app.construct.models import ScaffoldResult, SourceDocument

#: Canonical section headers, in exact canonical order.
CANONICAL_HEADERS = [
    "Environment & Dependencies",
    "Configuration & Global Parameters",
    "Data Ingestion",
    "Preprocessing & Feature Engineering",
    "Model Definition & Training",
    "Evaluation & Metrics",
    "Artifact Export (models, plots, reports)",
    "Conclusions & Next Steps",
]

#: Sections that carry a Phase 1 pin cell immediately after their header.
_PINNED_SECTIONS = {CANONICAL_HEADERS[0]: "env", CANONICAL_HEADERS[1]: "seeds"}

# Comment-only, ast.parse-safe code cells (the drafting pipeline's
# post-validation gate runs ast.parse over every code cell).
_ENV_PIN_SOURCE = (
    "# Environment & Dependencies (Phase 1 rule: pin the execution "
    "environment upfront).\n"
    "#\n"
    "# Declare the pinned dependency manifest for this notebook. "
    "Supported formats:\n"
    "#   - requirements.txt\n"
    "#   - conda.yaml\n"
    "#   - pyproject.toml\n"
    "#\n"
    "# Example (requirements.txt):\n"
    "#   nbformat==5.11.0\n"
    "#   numpy==2.1.0\n"
    "#   pandas==2.2.2\n"
    "#\n"
    "# Install the pinned environment before executing this notebook, "
    "for example:\n"
    "#   pip install -r requirements.txt\n"
)

_SEEDS_SOURCE = (
    "# Configuration & Global Parameters (Phase 1 rule: reproducibility "
    "controls).\n"
    "#\n"
    "# Set global random seeds, deterministic flags, and device "
    "configuration so results are reproducible across runs. Example:\n"
    "#\n"
    "#   import random\n"
    "#   import numpy as np\n"
    "#\n"
    "#   SEED = 42\n"
    "#   random.seed(SEED)\n"
    "#   np.random.seed(SEED)\n"
    "#   torch.manual_seed(SEED)  # when using PyTorch\n"
)


def _pin_cell(header: str) -> NotebookNode | None:
    """Return the Phase 1 pin code cell for a section, or ``None``."""
    pin = _PINNED_SECTIONS.get(header)
    if pin == "env":
        return nbformat.v4.new_code_cell(_ENV_PIN_SOURCE)
    if pin == "seeds":
        return nbformat.v4.new_code_cell(_SEEDS_SOURCE)
    return None


def build_scaffold(source: SourceDocument | None = None) -> ScaffoldResult:
    """Build the canonical notebook skeleton.

    Args:
        source: Optional source document. It is attached as LLM context
            only and never mapped into the skeleton structure (the skeleton
            is identical regardless of source).

    Returns:
        A :class:`ScaffoldResult`. The notebook is returned only after
        ``nbformat.validate`` passes; a validation failure returns
        ``valid=False`` with the validator's messages.
    """
    notebook = nbformat.v4.new_notebook(
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.14"},
        }
    )

    cells: list[NotebookNode] = []
    for header in CANONICAL_HEADERS:
        cells.append(nbformat.v4.new_markdown_cell(f"## {header}"))
        pin_cell = _pin_cell(header)
        if pin_cell is not None:
            cells.append(pin_cell)

    notebook.cells = cells

    try:
        nbformat.validate(notebook)
    except nbformat.ValidationError as exc:
        return ScaffoldResult(
            notebook=None,
            valid=False,
            validation_errors=[
                f"Scaffold failed nbformat validation: {exc}"
            ],
        )

    return ScaffoldResult(notebook=notebook, valid=True)
