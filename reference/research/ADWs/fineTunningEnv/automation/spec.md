# SPEC.md — Automated ML Notebook Audit & Repair Pipeline

## 1. Feature Overview

### Feature

**Automated ML Notebook Audit & Repair**

### Objective

Introduce an automated pipeline capable of auditing, validating, repairing, executing, and re-auditing Jupyter notebooks used for machine-learning experiments.

The feature must automate the following workflow:

```text
AUDIT
  ↓
FINDINGS > 8
  ↓
ROOT-CAUSE ANALYSIS
  ↓
PATCH
  ↓
EXECUTE
  ↓
FULL RE-AUDIT
  ↓
REGRESSION CHECK
  ↓
AUDIT AGAIN
  ↓
CLEAN PASS
```

The system must not declare success merely because a patch was proposed. A finding is resolved only when the corrected notebook no longer contains the underlying problem.

---

# 2. Motivation

Current notebook review is largely manual and difficult to reproduce.

A machine-learning notebook can be locally correct while still containing experimental problems such as:

* validation/test leakage;
* inconsistent preprocessing;
* incorrect metric definitions;
* incorrect model-selection criteria;
* checkpoint restoration errors;
* inconsistent train/validation/test protocols;
* undocumented changes to the experimental setup;
* plots that do not correspond to the reported metrics;
* conclusions unsupported by the actual experiment;
* non-reproducible random splits;
* artifacts generated from a different experiment than the one described.

The proposed feature converts notebook review into a repeatable QA process.

---

# 3. Goals

The feature SHALL:

1. Accept a `.ipynb` notebook as input.
2. Preserve the original notebook unchanged.
3. Perform deterministic static checks.
4. Perform semantic ML-experiment auditing.
5. Assign every genuine finding a severity from 1–10.
6. Treat only findings with severity `> 8` as patch candidates.
7. Distinguish `NEW` findings from issues related to previously identified issues.
8. Analyze the root cause of every patch candidate.
9. Apply minimal appropriate corrections.
10. Propagate protocol changes throughout the notebook.
11. Execute the corrected notebook when execution is possible.
12. Perform a full notebook re-audit after every patch iteration.
13. Detect regressions introduced by patches.
14. Repeat until:

```text
unresolved findings with severity > 8 == 0
```

15. Generate a complete audit report.
16. Preserve the audit history and every notebook iteration.

---

# 4. Non-Goals

This feature SHALL NOT:

* automatically fix every finding regardless of severity;
* rewrite the notebook unnecessarily;
* redesign the experiment merely because another design may be preferable;
* silently change the research objective;
* lower severity scores to force a PASS;
* treat deterministic execution as proof of experimental validity;
* replace human scientific judgment for ambiguous research conclusions;
* fabricate missing datasets, metrics, artifacts, or experimental results.

---

# 5. Core Audit Principle

The system must evaluate the notebook as a complete experimental artifact.

The following relationships must remain mutually consistent:

```text
CODE
 ↕
EXPERIMENTAL PROTOCOL
 ↕
DATA
 ↕
TRAINING
 ↕
VALIDATION / TEST
 ↕
METRICS
 ↕
PLOTS / TABLES
 ↕
ARTIFACTS
 ↕
MARKDOWN
 ↕
CONCLUSIONS
 ↕
QA
```

A problem that appears in one cell but affects another part of the experiment must be treated as a notebook-level issue.

---

# 6. Audit Categories

The auditor SHALL inspect at least the following categories.

## 6.1 Python Code

Check:

* syntax;
* undefined variables;
* invalid control flow;
* incorrect function calls;
* unreachable code;
* duplicate or conflicting definitions;
* import correctness;
* deprecated or incompatible APIs;
* execution ordering.

---

## 6.2 Tensor and Model Interfaces

Check:

* tensor shapes;
* batch dimensions;
* channel ordering;
* number of classes;
* model output dimensions;
* target-label compatibility;
* loss-function compatibility;
* device placement;
* dtype compatibility;
* checkpoint/model architecture compatibility.

Example invariant:

```python
logits.shape[0] == labels.shape[0]
```

---

## 6.3 Dataset and Data Splits

Check:

* train/validation/test separation;
* duplicate samples across splits;
* deterministic splitting;
* class coverage;
* class proportions;
* split reproducibility;
* accidental use of test data during training;
* accidental use of test data during model selection.

Critical invariant:

```text
TRAIN ∩ VALIDATION = ∅
TRAIN ∩ TEST       = ∅
VALIDATION ∩ TEST  = ∅
```

---

## 6.4 Preprocessing and Augmentation

Check:

* train-only augmentation;
* validation/test preprocessing;
* normalization consistency;
* image size;
* channel configuration;
* augmentation leakage;
* preprocessing applied differently between experiments.

---

## 6.5 Class Imbalance

Check:

* class counts;
* class weights;
* weighted loss;
* sampling strategy;
* metric interpretation;
* consistency between documented and implemented imbalance handling.

---

## 6.6 Training Logic

Check:

* optimizer;
* learning rate;
* scheduler;
* number of epochs;
* gradient handling;
* early stopping;
* checkpoint selection;
* restoration of the selected model;
* training/evaluation mode;
* zeroing gradients.

---

## 6.7 Model Selection

Check that:

```text
selection metric
        ↓
best checkpoint
        ↓
restored model
        ↓
final evaluation
```

is internally consistent.

The system must identify cases where:

* one metric selects the model;
* another metric is reported as if it selected the model;
* the best checkpoint is not restored;
* test data is used for model selection.

---

## 6.8 Transfer-Learning Variants

For experiments comparing variants, check that the variants differ only in their intended experimental factor.

For example:

```text
Frozen backbone
Fine-tuning
PEFT / LoRA
From-scratch baseline
```

must use the same:

* dataset;
* split;
* preprocessing;
* class weighting;
* evaluation protocol;
* metric definitions;
* comparison methodology.

---

## 6.9 Metrics

Check:

* metric definitions;
* implementation;
* label ordering;
* averaging method;
* handling of zero divisions;
* binary vs multiclass interpretation;
* train/validation/test association;
* consistency with markdown formulas.

---

## 6.10 Plots and Tables

Check:

* data source;
* metric source;
* axis labels;
* legends;
* experiment names;
* epoch numbering;
* reported values;
* table columns;
* plot values;
* comparison consistency.

A plot must represent the same experiment described by the surrounding documentation.

---

## 6.11 Saved Artifacts

Check:

* checkpoints;
* CSV files;
* JSON files;
* plots;
* confusion matrices;
* manifests;
* metric reports;
* artifact naming;
* artifact provenance.

Artifacts must correspond to the corrected experiment.

---

## 6.12 Reproducibility

Check:

* random seeds;
* deterministic splits;
* deterministic experiment configuration;
* package/API assumptions;
* runtime requirements;
* device assumptions;
* dataset assumptions;
* artifact metadata.

---

## 6.13 Markdown and Documentation

Check:

* code vs markdown consistency;
* outdated descriptions;
* obsolete experimental protocols;
* incorrect formulas;
* incorrect conclusions;
* incorrect dataset descriptions;
* incorrect metric descriptions.

---

## 6.14 Conclusions

Check whether conclusions are actually supported by:

```text
DATA
→ EXPERIMENT
→ METRICS
→ STATISTICS
→ OBSERVATIONS
```

The auditor must flag conclusions that assert more than the experiment demonstrates.

---

## 6.15 QA and Validation

Check:

* internal assertions;
* expected artifacts;
* dataset invariants;
* split invariants;
* metric ranges;
* checkpoint invariants;
* execution state;
* final validation checks.

---

# 7. Severity Model

Every genuine finding MUST receive a severity from 1–10.

| Severity | Meaning                                                                 |
| -------: | ----------------------------------------------------------------------- |
|      1–2 | Cosmetic/minor                                                          |
|      3–4 | Low-impact quality issue                                                |
|      5–6 | Moderate correctness/reproducibility issue                              |
|      7–8 | Significant issue but not automatically patched                         |
|        9 | Severe correctness/experimental-validity problem                        |
|       10 | Critical failure affecting correctness, safety, or fundamental validity |

Only:

```text
severity > 8
```

requires automatic patching.

The system MUST NOT lower severity merely to reach the stopping condition.

---

# 8. Finding Schema

All findings SHALL use a structured schema similar to:

```json
{
  "id": "F-001",
  "severity": 9,
  "classification": "NEW",
  "category": "experimental_validity",
  "location": {
    "cell": 38,
    "line": 12
  },
  "issue": "...",
  "root_cause": "...",
  "impact": "...",
  "correction": "...",
  "status": "unresolved"
}
```

Allowed classifications:

```text
NEW
RELATED_TO_OLD_ISSUE
```

Allowed statuses:

```text
unresolved
patched
resolved
recurring
wont_fix
```

---

# 9. Previous-Issue Tracking

The system SHALL maintain an issue history.

Example:

```json
{
  "signature": "validation_used_for_model_selection_and_final_evaluation",
  "category": "experimental_validity",
  "severity": 9,
  "status": "resolved"
}
```

A new finding must be compared against previous findings.

The system must classify an issue as related to an old issue if:

* the underlying root cause is the same;
* the issue has recurred;
* the previous correction was incomplete;
* the previous correction caused a related inconsistency.

Wording alone must not determine recurrence.

---

# 10. Original Notebook Preservation

The original notebook SHALL be immutable.

Recommended structure:

```text
audit-runs/
└── <timestamp>/
    ├── original.ipynb
    ├── iterations/
    │   ├── iteration-001.ipynb
    │   ├── iteration-002.ipynb
    │   └── iteration-003.ipynb
    │
    ├── audits/
    │   ├── audit-001.json
    │   ├── audit-002.json
    │   └── audit-003.json
    │
    ├── artifacts/
    └── report.md
```

The original notebook must always remain available for comparison.

---

# 11. Notebook Intermediate Representation

The system SHOULD parse the notebook into an intermediate representation.

Example:

```python
NotebookModel(
    cells=[...],
    datasets=[...],
    experiments=[...],
    metrics=[...],
    artifacts=[...],
    models=[...],
    configuration={...}
)
```

The representation should capture:

* cells;
* variables;
* imports;
* functions;
* datasets;
* splits;
* models;
* optimizers;
* schedulers;
* metrics;
* plots;
* artifacts;
* configuration;
* experiment variants.

This allows semantic checks to operate over the notebook as a graph rather than as isolated cells.

---

# 12. Static Audit Engine

The static audit engine SHALL handle deterministic checks.

Examples:

```text
Notebook JSON validity
Python syntax
AST analysis
Imports
Variable definitions
Variable usage
Cell execution order
Known API misuse
Artifact references
Static split definitions
Static seed configuration
```

Static checks SHOULD NOT depend on an LLM.

---

# 13. ML QA Engine

The ML QA engine SHALL execute deterministic runtime checks when possible.

Examples:

```python
assert train_ids.isdisjoint(val_ids)
assert train_ids.isdisjoint(test_ids)
assert val_ids.isdisjoint(test_ids)
```

```python
assert logits.shape[0] == labels.shape[0]
```

```python
assert 0 <= accuracy <= 1
assert 0 <= precision <= 1
assert 0 <= recall <= 1
assert 0 <= f1 <= 1
```

```python
assert checkpoint.exists()
```

The exact checks should be extensible.

---

# 14. Semantic LLM Auditor

The LLM SHALL focus on problems that are difficult to determine mechanically.

It should inspect:

* experimental validity;
* protocol consistency;
* documentation consistency;
* metric semantics;
* model-selection methodology;
* conclusions;
* root causes;
* interactions between distant notebook sections.

The LLM must return structured findings rather than unrestricted prose.

---

# 15. Root-Cause Analysis

Every finding with:

```text
severity > 8
```

must undergo root-cause analysis before patching.

The analysis must identify:

1. exact issue;
2. exact location;
3. severity;
4. NEW/RELATED classification;
5. underlying cause;
6. experimental impact;
7. minimal correction;
8. downstream components affected.

---

# 16. Patch Engine

The patch engine SHALL modify only findings with:

```text
severity > 8
```

unless explicitly overridden by the user.

Patches should be minimal.

A patch must preserve:

* original research objective;
* experiment intent;
* existing valid implementation;
* reproducibility assumptions.

The patch engine must identify every downstream component affected by a protocol change.

---

# 17. Protocol Propagation

If a patch changes the experimental protocol, the system must inspect:

```text
data
 ↓
training
 ↓
validation
 ↓
test
 ↓
metrics
 ↓
plots
 ↓
tables
 ↓
artifacts
 ↓
markdown
 ↓
conclusions
 ↓
QA
```

Example:

If validation/test leakage is fixed, changing only the split code is insufficient.

The system must also inspect:

* training loaders;
* validation loaders;
* test loaders;
* model-selection logic;
* final metrics;
* confusion matrices;
* comparison tables;
* plots;
* saved checkpoints;
* artifact metadata;
* markdown;
* conclusions;
* QA assertions.

---

# 18. Notebook Execution

After applying a patch, the notebook SHOULD be executed automatically.

Recommended technologies:

```text
nbclient
jupyter nbconvert
papermill
```

Execution errors become audit findings.

Example:

```json
{
  "category": "execution",
  "severity": 10,
  "issue": "Notebook execution failed.",
  "location": {
    "cell": 42
  }
}
```

The system must never report PASS when the corrected notebook cannot execute and the failure is unresolved.

---

# 19. Regression Audit

After every patch:

```text
DO NOT audit only the patched cell.
```

Instead:

```text
FULL NOTEBOOK RE-AUDIT
```

The auditor must inspect:

* original issue;
* related cells;
* downstream protocol;
* artifacts;
* documentation;
* conclusions;
* QA;
* new inconsistencies.

---

# 20. Recurring Issue Handling

If an issue persists after a patch:

```text
1. Return to ORIGINAL notebook context.
2. Reassess root cause.
3. Determine why the previous patch failed.
4. Do not blindly repeat the patch.
5. Design a materially different correction.
6. Apply it.
7. Execute.
8. Perform a full audit.
```

Example:

```text
Patch 1:
Change validation loader.

Still broken:
Final metrics still use validation.

Root cause:
Evaluation architecture assumes validation is the final evaluation dataset.

Patch 2:
Introduce independent test loader and propagate it through
metrics, plots, artifacts, and conclusions.
```

---

# 21. Iteration Controller

The controller SHALL implement:

```python
while True:

    findings = audit(notebook)

    critical = [
        f for f in findings
        if f.severity > 8
        and f.status == "unresolved"
    ]

    if not critical:
        break

    root_causes = analyze_root_causes(critical)

    notebook = apply_patches(
        notebook,
        root_causes
    )

    execute(notebook)

    run_runtime_qa(notebook)

    save_iteration(notebook)
```

The loop must have a configurable maximum iteration count to prevent infinite execution.

Example:

```text
MAX_ITERATIONS = 10
```

If the maximum is reached while unresolved >8 findings remain:

```text
STATUS = FAILED
```

It must NOT report PASS.

---

# 22. Final Pass Condition

The only valid automated PASS condition is:

```python
unresolved_findings = [
    finding
    for finding in findings
    if finding.severity > 8
    and finding.status != "resolved"
]

assert len(unresolved_findings) == 0
```

Additionally:

```text
Notebook executes successfully
AND
final QA passes
AND
no >8 regression exists
```

Therefore:

```text
PASS =
    unresolved >8 == 0
    AND execution == SUCCESS
    AND QA == PASS
    AND regression == NONE
```

---

# 23. CLI

The feature SHOULD expose a CLI.

### Audit

```bash
nb-audit audit notebook.ipynb
```

### Audit with configuration

```bash
nb-audit audit notebook.ipynb \
    --max-iterations 10 \
    --severity-threshold 8
```

### Static audit only

```bash
nb-audit static notebook.ipynb
```

### Execute only

```bash
nb-audit execute notebook.ipynb
```

### Generate report

```bash
nb-audit report audit-runs/<run-id>
```

---

# 24. Configuration

Example:

```yaml
audit:
  severity_threshold: 8
  max_iterations: 10
  execute_notebook: true
  preserve_original: true

llm:
  model: <configured-model>
  temperature: 0

execution:
  timeout_seconds: 3600
  allow_network: false

qa:
  require_clean_execution: true
  require_artifacts: true
  require_reproducibility_checks: true
```

The project must allow these values to be overridden without modifying source code.

---

# 25. Report Format

The final report SHALL contain:

```markdown
# Final Audit

## Initial Findings > 8

### F-001
- Severity:
- Classification:
- Location:
- Root cause:
- Patch:
- Result:

## Iteration History

### Iteration 1
- Findings:
- Patches:
- Regressions:
- Result:

### Iteration 2
...

## Recurring Issues

...

## Final Verification

- [ ] 0 unresolved findings > 8
- [ ] no previous >8 issue remains unresolved
- [ ] no new >8 regression
- [ ] code and documentation agree
- [ ] experimental protocol agrees with implementation
- [ ] metrics match definitions
- [ ] plots/tables match metrics
- [ ] artifacts correspond to experiment
- [ ] conclusions are supported
- [ ] reproducibility/QA checks pass

## FINAL STATUS

Unresolved findings > 8: 0

Status: PASS
```

---

# 26. Artifact Requirements

Every audit run SHOULD produce:

```text
original.ipynb
final.ipynb
audit.json
report.md
```

and:

```text
iterations/
audits/
artifacts/
logs/
```

Each iteration should contain enough information to reproduce why a patch was applied.

---

# 27. Safety and Patch Constraints

The patch engine must:

* never modify the original notebook;
* never fabricate experimental results;
* never invent missing datasets;
* never silently change the research objective;
* never remove an experiment merely to make QA pass;
* never lower severity;
* never suppress execution errors;
* never overwrite audit history.

Every patch must be attributable to a finding.

---

# 28. Testing Strategy

The feature itself must have automated tests.

## Unit tests

Test:

* notebook parser;
* AST analyzer;
* finding schema;
* severity filtering;
* recurrence detection;
* patch application;
* artifact tracking.

## Integration tests

Use deliberately broken notebooks containing:

```text
validation leakage
incorrect tensor shapes
missing checkpoint restoration
incorrect metric
missing seed
documentation mismatch
artifact mismatch
```

The auditor must detect the expected issue.

## Regression tests

For every fixed high-severity issue, preserve a minimal notebook fixture reproducing the original failure.

Example:

```text
tests/fixtures/
├── validation_leakage.ipynb
├── checkpoint_not_restored.ipynb
├── metric_mismatch.ipynb
└── train_test_overlap.ipynb
```

---

# 29. Acceptance Criteria

The feature is considered complete when it can:

### AC-01

Accept a Jupyter notebook.

### AC-02

Create an immutable copy of the original.

### AC-03

Perform static analysis.

### AC-04

Perform semantic ML auditing.

### AC-05

Return structured findings with severity 1–10.

### AC-06

Automatically select only:

```text
severity > 8
```

for patching.

### AC-07

Distinguish NEW vs RELATED_TO_OLD_ISSUE.

### AC-08

Perform root-cause analysis.

### AC-09

Apply patches automatically.

### AC-10

Execute the patched notebook.

### AC-11

Perform a complete notebook re-audit.

### AC-12

Detect patch-induced regressions.

### AC-13

Handle recurring issues using a different correction strategy.

### AC-14

Preserve every iteration.

### AC-15

Generate a final audit report.

### AC-16

Never report PASS while unresolved >8 findings remain.

### AC-17

Report:

```text
Unresolved findings > 8: 0
Status: PASS
```

only after the complete audit pipeline succeeds.

---

# 30. Proposed Architecture

```text
                    ┌────────────────────┐
                    │     CLI / API      │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Notebook Manager   │
                    │ original + copies  │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Notebook Parser    │
                    │ AST + IR           │
                    └─────────┬──────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
      ┌──────────────────┐        ┌──────────────────┐
      │ Static Audit     │        │ Semantic Audit   │
      │ Engine           │        │ LLM              │
      └────────┬─────────┘        └────────┬─────────┘
               │                           │
               └─────────────┬─────────────┘
                             ▼
                    ┌────────────────────┐
                    │ Finding Manager    │
                    │ severity + history │
                    └─────────┬──────────┘
                              │
                         severity > 8
                              │
                              ▼
                    ┌────────────────────┐
                    │ Root Cause Agent   │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ Patch Agent        │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ Notebook Executor  │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ Runtime ML QA      │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ Regression Audit   │
                    └─────────┬──────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                 findings             clean
                  > 8                   │
                    │                   ▼
                    └──────────────► REPORT
```

---

# 31. Implementation Phases

## Phase 1 — Notebook Infrastructure

Implement:

* notebook loading;
* notebook saving;
* immutable originals;
* iteration management;
* audit-run directory;
* CLI.

## Phase 2 — Static Analysis

Implement:

* syntax validation;
* AST analysis;
* import analysis;
* variable analysis;
* notebook execution-order checks.

## Phase 3 — ML QA

Implement:

* dataset checks;
* split checks;
* tensor checks;
* metric checks;
* checkpoint checks;
* artifact checks;
* reproducibility checks.

## Phase 4 — LLM Semantic Audit

Implement:

* structured audit prompt;
* finding schema;
* semantic consistency checks;
* experimental-validity analysis.

## Phase 5 — Automated Repair

Implement:

* root-cause analysis;
* patch generation;
* notebook cell modification;
* patch validation.

## Phase 6 — Iterative Regression Loop

Implement:

```text
AUDIT
→ PATCH
→ EXECUTE
→ QA
→ FULL RE-AUDIT
```

with recurring-issue detection.

## Phase 7 — Reporting

Implement:

* JSON report;
* Markdown report;
* iteration history;
* final PASS/FAIL status.

---

# 32. Recommended Initial Scope

The first implementation should NOT attempt to support every possible ML framework.

The MVP should target:

```text
Python
Jupyter Notebook
PyTorch
torchvision
scikit-learn
pandas
matplotlib
```

and focus on:

```text
dataset splits
training
validation
test evaluation
metrics
checkpoints
reproducibility
plots
artifacts
experimental protocol consistency
```

Once the architecture is stable, support can be extended to:

```text
TensorFlow
Keras
XGBoost
LightGBM
Hugging Face Transformers
PEFT
```

---

# 33. Definition of Done

This feature is complete when the project can take an arbitrary supported ML notebook and automatically perform:

```text
INPUT NOTEBOOK
       ↓
STATIC AUDIT
       ↓
SEMANTIC AUDIT
       ↓
SEVERITY CLASSIFICATION
       ↓
ROOT-CAUSE ANALYSIS
       ↓
PATCH >8 FINDINGS
       ↓
EXECUTE
       ↓
RUNTIME QA
       ↓
FULL RE-AUDIT
       ↓
REGRESSION CHECK
       ↓
REPEAT IF NECESSARY
       ↓
FINAL REPORT
```

and guarantees the following final invariant:

```text
UNRESOLVED FINDINGS WITH SEVERITY > 8 = 0
```

The system must distinguish between:

```text
"the model proposed a fix"
```

and:

```text
"the notebook was fixed and verified."
```

Only the second condition can produce:

```text
Status: PASS
```
