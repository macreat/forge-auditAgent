"""Per-section drafting prompts encoding the Phase 2 discipline rules.

Pure functions: no state, no I/O. The writer passes the output of
:func:`section_instructions` as the provider's system instructions, so the
same discipline rules apply to every section of every run.
"""

from __future__ import annotations

from app.construct.scaffold import CANONICAL_HEADERS

#: Phase 2 discipline rules from Part I of NotebookBuildAudit.md, verbatim.
DISCIPLINE_RULES = [
    "Work through one section at a time (Divide and Conquer principle).",
    "Accompany every code cell with a markdown explanation of intent and "
    "expected output.",
    "Avoid burying logic inside loops or helper calls without commentary.",
    "Prefer explicit variable passing over hidden or global state to "
    "maintain cell independence.",
    "Summarize repetitive code patterns with a general description and "
    "highlight any meaningful variations; treat three or more similar "
    "blocks as a refactoring candidate.",
    "Route all persisted outputs (models, plots, reports) through a single, "
    "versioned export convention defined at the start of the section; never "
    "write artifacts ad hoc from arbitrary cells.",
]

OUTPUT_FORMAT = """\
Every section output MUST use the strict line-based format below.

A section consists of one or more blocks, each introduced by a marker line:
  ===MARKDOWN===  — the following lines form one markdown cell
  ===CODE===      — the following lines form one code cell

Rules:
- Every section output MUST contain at least one ===MARKDOWN=== block.
- ===CODE=== blocks are optional; blocks are repeatable in any order.
- The line after a marker begins that block's content; the block ends at the
  next marker line (or at the end of the output).
- Content lines are taken verbatim. To include a literal line equal to a
  marker inside content, prefix it with a backslash (for example
  \\===CODE===); the parser removes exactly one leading backslash.
"""


def section_instructions(header: str) -> str:
    """Compose the drafting instructions for one canonical section.

    Args:
        header: The canonical section header being drafted (one of
            :data:`app.construct.scaffold.CANONICAL_HEADERS`).

    Returns:
        Instructions for the provider's system field: the section identity,
        the Phase 2 discipline rules, and the strict output format grammar.
    """
    rules = "\n".join(f"- {rule}" for rule in DISCIPLINE_RULES)
    return (
        f"You are drafting the \"{header}\" section of a Jupyter notebook. "
        f"The section header is: {header}\n\n"
        "Discipline rules (follow verbatim):\n"
        f"{rules}\n\n"
        "Output format:\n"
        f"{OUTPUT_FORMAT}"
    )


def drafting_system_prompt() -> str:
    """Compose the global drafting system prompt.

    The same discipline rules apply across all sections; the output format
    grammar is included so the provider never needs prior context.
    """
    rules = "\n".join(f"- {rule}" for rule in DISCIPLINE_RULES)
    return (
        "You are authoring a reproducible Jupyter notebook following the "
        "Notebook Construction Framework. Sections are drafted one at a "
        "time, in this canonical order:\n"
        + "\n".join(f"{i}. {header}" for i, header in enumerate(CANONICAL_HEADERS, 1))
        + "\n\nDiscipline rules (follow verbatim):\n"
        + rules
        + "\n\nOutput format:\n"
        + OUTPUT_FORMAT
    )
