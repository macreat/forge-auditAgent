
# test-prompts-app – Multi-LLM Audit Comparison

## Overview

The application executes the same audit prompt against multiple LLMs and stores the raw JSON returned by each model without modifying it. The goal is **not** to determine which model is "correct", but to measure consistency, completeness, and variability between implementations.

The audit prompt instructs each model to behave as a factual evidence-extraction sensor for Jupyter notebooks, producing a structured JSON containing:

- `overall_purpose`
- `pipeline_summary`
- `observations`
- `complex_functions`
- `cross_reference_discrepancies`

The application should preserve the original output for traceability.

---

# New Comparison Functionality

A new **Experiment Comparison** view compares outputs from multiple LLMs.

Example:

| Model | Overall Purpose | # Observations | # Complex Functions | JSON Valid | Duration |
|--------|-----------------|---------------:|--------------------:|-----------|---------:|
| GPT-5 | ✔ | 8 | 2 | ✔ | 3.1 s |
| Claude | ✔ | 7 | 1 | ✔ | 3.8 s |
| Llama | ✔ | 6 | 2 | ✔ | 12.4 s |

---

# Variability Analysis

Instead of comparing text literally, the application compares the JSON structure.

## Observation Coverage

| Criterion | GPT | Claude | Llama |
|-----------|-----|---------|--------|
|1.1|✔|✔|✔|
|1.2|✔|✔|✖|
|1.3|✔|✔|✔|
|1.4|✔|✖|✔|
|2.1|✔|✔|✔|
|2.2|✖|✖|✖|
|2.3|✔|✔|✔|
|2.4|✔|✔|✔|
|2.5|✔|✔|✔|

---

## Atomic Observation Variability

For every `(criterion_id, cell_id)` pair:

| Criterion | Cell | GPT | Claude | Llama |
|-----------|------|-----|---------|--------|
|2.5|C024|Caching absent|Checkpoint absent|No caching detected|

This highlights semantic variability while preserving the original evidence.

---

## Complex Function Detection

| Function | GPT | Claude | Llama |
|----------|-----|---------|--------|
|MultiScaleLSTM.forward|✔|✔|✔|
|run_rolling_origin_validation|✔|✔|✖|

---

## Summary Variability

Compare:

- overall_purpose
- pipeline_summary

using semantic similarity rather than exact text.

---

## JSON Validation

Each response is validated against the SensorOutput schema.

Display:

- Valid JSON
- Missing fields
- Extra fields
- Invalid types

---

## Metrics

Per model:

- execution time
- token usage (if available)
- output size
- observation count
- complex function count
- discrepancy count

---

## Raw JSON Viewer

Every model retains its original JSON for inspection.

---

## Suggested UI

Tabs:

1. Experiment
2. Raw Outputs
3. Observation Matrix
4. Variability Analysis
5. Metrics

---

## Benefits

This allows researchers to identify:

- omitted observations
- additional observations
- wording variability
- structural differences
- schema compliance
- reproducibility across models

The comparison focuses on factual extraction differences rather than subjective scoring, making it suitable for benchmarking notebook-auditing prompts across heterogeneous LLMs.
