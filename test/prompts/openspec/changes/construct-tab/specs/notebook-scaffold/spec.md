# Notebook Scaffold Specification

## Purpose

Build a generic, reproducible notebook skeleton with `nbformat` (added to `requirements.txt`, PyInstaller-safe). The scaffold produces a v4 notebook with the eight canonical markdown section headers in canonical order, an environment-pin code cell, and a reproducibility/seeds code cell. The scaffold is generic: the source document is attached as context for the LLM and is never mapped into the skeleton structure.

## Requirements

### Requirement: Canonical section headers

The scaffold MUST create markdown cells with exactly these eight headers, in this exact order:

1. Environment & Dependencies
2. Configuration & Global Parameters
3. Data Ingestion
4. Preprocessing & Feature Engineering
5. Model Definition & Training
6. Evaluation & Metrics
7. Artifact Export (models, plots, reports)
8. Conclusions & Next Steps

#### Scenario: Headers present in canonical order

- GIVEN a scaffold request with no source mapping
- WHEN the scaffold builds the notebook
- THEN eight markdown cells contain the eight headers above
- AND the header order matches the canonical list exactly

### Requirement: Environment pinning cell

The scaffold MUST include a code cell pinning the execution environment via `requirements.txt`, `conda.yaml`, or `pyproject.toml`, following the Phase 1 rule: pin the execution environment upfront.

#### Scenario: Environment pin cell present

- GIVEN a scaffolded notebook
- WHEN the notebook is inspected
- THEN a code cell declares pinned dependencies via one of the three supported manifest formats
- AND the cell is placed in the Environment & Dependencies section

### Requirement: Reproducibility cell

The scaffold MUST include a code cell setting global reproducibility controls: random seeds, deterministic flags, and device configuration, following the Phase 1 rule.

#### Scenario: Seeds and device config present

- GIVEN a scaffolded notebook
- WHEN the notebook is inspected
- THEN a code cell sets random seeds, deterministic flags, and device configuration
- AND the cell is placed in the Configuration & Global Parameters section

### Requirement: Valid nbformat notebook

The scaffold MUST produce an nbformat v4 notebook and MUST run `nbformat.validate` on it before returning. A scaffold that fails validation MUST NOT be returned to the pipeline.

#### Scenario: Validation gate passes

- GIVEN a completed scaffold
- WHEN the scaffold calls `nbformat.validate`
- THEN validation passes and the notebook is returned

#### Scenario: Invalid scaffold rejected

- GIVEN a scaffold that fails nbformat validation
- WHEN the validation gate runs
- THEN the pipeline receives an invalid result
- AND the notebook is not returned for drafting

### Requirement: Generic skeleton only

The scaffold MUST NOT map source content into the skeleton structure. The source document is passed to the LLM as context only; no domain-specific parsing or structure inference occurs.

#### Scenario: Source does not alter skeleton

- GIVEN any source document (e.g., a GitHub README or a Kaggle CSV)
- WHEN the scaffold builds the notebook
- THEN the skeleton structure is identical regardless of source
- AND the source is attached only as LLM context

### Requirement: Phase 2 drafting discipline

The drafting phase MUST follow these Phase 2 discipline rules verbatim:

- Work through one section at a time (Divide and Conquer principle).
- Accompany every code cell with a markdown explanation of intent and expected output.
- Avoid burying logic inside loops or helper calls without commentary.
- Prefer explicit variable passing over hidden or global state to maintain cell independence.
- Summarize repetitive code patterns with a general description and highlight any meaningful variations; three or more similar blocks should be treated as a refactoring candidate.
- Route all persisted outputs (models, plots, reports) through a single, versioned export convention defined at the start of the section — never write artifacts ad hoc from arbitrary cells.

#### Scenario: Discipline rules applied

- GIVEN a drafted notebook
- WHEN the notebook is reviewed
- THEN every code cell has an accompanying markdown explanation
- AND sections are drafted one at a time in canonical order

#### Scenario: Repetition flagged

- GIVEN three or more similar code blocks in a draft
- WHEN drafting completes
- THEN the draft summarizes the repeated pattern as a refactoring candidate
- AND meaningful variations are highlighted
