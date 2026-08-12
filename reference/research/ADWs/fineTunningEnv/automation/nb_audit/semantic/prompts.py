"""Structured audit prompt and the §6 category map for the semantic LLM auditor.

The semantic auditor (spec §14) targets problems that are hard to determine
mechanically: experimental validity, protocol consistency, documentation
consistency, metric semantics, model-selection methodology, conclusions, root
causes, and interactions between distant notebook sections.

Its findings are ADVISORY: they can only ever *add* to the static/ML-QA
findings, never remove them, and an outage degrades the pipeline to static-only
without flipping PASS/FAIL. The prompt therefore demands strict JSON so every
returned finding can be schema-validated before entering the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from nb_audit.ir import NotebookModel


# --------------------------------------------------------------------------- #
# Category map (spec §6)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CategorySpec:
    """One audit category from spec §6: stable key + human name + checklist."""

    key: str
    name: str
    section: str
    checks: tuple[str, ...]


# The 15 audit categories of spec §6.1–§6.15, in spec order. ``key`` is the
# machine-readable category used in findings; ``name``/``section`` are for the
# human-readable prompt.
AUDIT_CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec(
        "python_code",
        "Python Code",
        "6.1",
        (
            "syntax",
            "undefined variables",
            "invalid control flow",
            "incorrect function calls",
            "unreachable code",
            "duplicate or conflicting definitions",
            "import correctness",
            "deprecated or incompatible APIs",
            "execution ordering",
        ),
    ),
    CategorySpec(
        "tensor_interfaces",
        "Tensor and Model Interfaces",
        "6.2",
        (
            "tensor shapes",
            "batch dimensions",
            "channel ordering",
            "number of classes",
            "model output dimensions",
            "target-label compatibility",
            "loss-function compatibility",
            "device placement",
            "dtype compatibility",
            "checkpoint/model architecture compatibility",
        ),
    ),
    CategorySpec(
        "data_splits",
        "Dataset and Data Splits",
        "6.3",
        (
            "train/validation/test separation",
            "duplicate samples across splits",
            "deterministic splitting",
            "class coverage",
            "class proportions",
            "split reproducibility",
            "test data used during training",
            "test data used during model selection",
        ),
    ),
    CategorySpec(
        "preprocessing",
        "Preprocessing and Augmentation",
        "6.4",
        (
            "train-only augmentation",
            "validation/test preprocessing",
            "normalization consistency",
            "image size",
            "channel configuration",
            "augmentation leakage",
            "preprocessing differences between experiments",
        ),
    ),
    CategorySpec(
        "class_imbalance",
        "Class Imbalance",
        "6.5",
        (
            "class counts",
            "class weights",
            "weighted loss",
            "sampling strategy",
            "metric interpretation",
            "consistency between documented and implemented imbalance handling",
        ),
    ),
    CategorySpec(
        "training_logic",
        "Training Logic",
        "6.6",
        (
            "optimizer",
            "learning rate",
            "scheduler",
            "number of epochs",
            "gradient handling",
            "early stopping",
            "checkpoint selection",
            "restoration of the selected model",
            "training/evaluation mode",
            "zeroing gradients",
        ),
    ),
    CategorySpec(
        "model_selection",
        "Model Selection",
        "6.7",
        (
            "selection metric consistency",
            "best checkpoint restoration",
            "metric that selected the model vs metric reported",
            "test data used for model selection",
        ),
    ),
    CategorySpec(
        "transfer_variants",
        "Transfer-Learning Variants",
        "6.8",
        (
            "variants differ only in the intended experimental factor",
            "frozen backbone vs fine-tuning vs PEFT/LoRA vs from-scratch",
            "shared dataset, split, preprocessing, class weighting",
            "shared evaluation protocol, metric definitions, comparison methodology",
        ),
    ),
    CategorySpec(
        "metrics",
        "Metrics",
        "6.9",
        (
            "metric definitions",
            "implementation",
            "label ordering",
            "averaging method",
            "zero-division handling",
            "binary vs multiclass interpretation",
            "train/validation/test association",
            "consistency with markdown formulas",
        ),
    ),
    CategorySpec(
        "plots_tables",
        "Plots and Tables",
        "6.10",
        (
            "data source",
            "metric source",
            "axis labels",
            "legends",
            "experiment names",
            "epoch numbering",
            "reported values",
            "table columns",
            "plot values",
            "comparison consistency",
            "plot matches surrounding documentation",
        ),
    ),
    CategorySpec(
        "artifacts",
        "Saved Artifacts",
        "6.11",
        (
            "checkpoints",
            "CSV files",
            "JSON files",
            "plots",
            "confusion matrices",
            "manifests",
            "metric reports",
            "artifact naming",
            "artifact provenance",
            "artifacts correspond to the corrected experiment",
        ),
    ),
    CategorySpec(
        "reproducibility",
        "Reproducibility",
        "6.12",
        (
            "random seeds",
            "deterministic splits",
            "deterministic experiment configuration",
            "package/API assumptions",
            "runtime requirements",
            "device assumptions",
            "dataset assumptions",
            "artifact metadata",
        ),
    ),
    CategorySpec(
        "documentation",
        "Markdown and Documentation",
        "6.13",
        (
            "code vs markdown consistency",
            "outdated descriptions",
            "obsolete experimental protocols",
            "incorrect formulas",
            "incorrect conclusions",
            "incorrect dataset descriptions",
            "incorrect metric descriptions",
        ),
    ),
    CategorySpec(
        "conclusions",
        "Conclusions",
        "6.14",
        (
            "conclusions supported by data → experiment → metrics → statistics → observations",
            "flag conclusions that assert more than the experiment demonstrates",
        ),
    ),
    CategorySpec(
        "qa_validation",
        "QA and Validation",
        "6.15",
        (
            "internal assertions",
            "expected artifacts",
            "dataset invariants",
            "split invariants",
            "metric ranges",
            "checkpoint invariants",
            "execution state",
            "final validation checks",
        ),
    ),
)


def category_keys() -> tuple[str, ...]:
    """Return the 15 stable machine-readable category keys, in spec order."""
    return tuple(c.key for c in AUDIT_CATEGORIES)


# --------------------------------------------------------------------------- #
# IR summary
# --------------------------------------------------------------------------- #
_MARKDOWN_LIMIT = 800


def _render_ir_summary(ir: NotebookModel) -> str:
    """Render a compact, deterministic summary of the notebook IR for the prompt."""
    lines: list[str] = []

    def section(title: str, refs: tuple) -> None:
        if not refs:
            return
        names = ", ".join(str(getattr(r, "name", r)) for r in refs)
        lines.append(f"{title}: {names}")

    section("Imports", ir.imports)
    section("Functions", ir.functions)
    section("Variables", ir.variables)
    section("Datasets", ir.datasets)
    section("Splits", ir.splits)
    section("Models", ir.models)
    section("Optimizers", ir.optimizers)
    section("Schedulers", ir.schedulers)
    section("Metrics", ir.metrics)
    section("Plots", ir.plots)
    section("Artifacts", ir.artifacts)
    section("Experiment variants", ir.experiment_variants)
    if ir.configuration:
        lines.append(f"Configuration: {ir.configuration!r}")

    markdown_cells = [c for c in ir.cells if c.cell_type == "markdown"]
    if markdown_cells:
        lines.append("Markdown cells:")
        for cell in markdown_cells:
            text = cell.source.strip().replace("\n", " ")
            if len(text) > _MARKDOWN_LIMIT:
                text = text[:_MARKDOWN_LIMIT] + "…"
            lines.append(f"  [cell {cell.index}] {text}")

    return "\n".join(lines) if lines else "(no code or markdown detected)"


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
def render_audit_prompt(ir: NotebookModel) -> str:
    """Render the full audit prompt for ``ir`` (categories + IR summary + schema).

    The prompt instructs the model to return strict JSON (a single object with a
    ``findings`` list) so :func:`~nb_audit.semantic.backend.Backend.validate_findings`
    can schema-validate every entry. The 15 spec §6 categories are all referenced.
    """
    categories = "\n".join(
        f"- {c.key} — {c.name} (§{c.section}): {', '.join(c.checks)}"
        for c in AUDIT_CATEGORIES
    )
    return (
        "You are an ML-experiment auditor. Inspect the following Jupyter notebook "
        "as a complete experimental artifact and report ONLY genuine problems that "
        "are hard to determine mechanically (experimental validity, protocol "
        "consistency, documentation consistency, metric semantics, model-selection "
        "methodology, conclusions, root causes, interactions between distant "
        "sections).\n\n"
        "Audit categories (spec §6.1–§6.15):\n"
        f"{categories}\n\n"
        "Notebook IR summary:\n"
        f"{_render_ir_summary(ir)}\n\n"
        'Respond with a single JSON object of the form {"findings": [<finding>, ...]} '
        "and nothing else (no markdown fences, no prose). Each finding is an object "
        "with these fields:\n"
        '  "severity"       (int, REQUIRED, 1–10)\n'
        '  "category"       (str, REQUIRED, one of the category keys above)\n'
        '  "issue"          (str, REQUIRED, concise description)\n'
        '  "location"       (object, {"cell": str, "line": int|null})\n'
        '  "root_cause"     (str)\n'
        '  "impact"         (str)\n'
        '  "correction"     (str)\n'
        '  "classification" (str, "NEW" | "RELATED_TO_OLD_ISSUE")\n\n'
        "If the notebook is sound, return {\"findings\": []}. Never invent findings, "
        "never fabricate data, and do not lower severity to force a clean result."
    )
