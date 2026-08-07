# AI-Ready Specification: forge-auditAgent — Modular Agentic AI Environment

## Document Metadata

| Field | Value |
|---|---|
| **Document** | AI-Ready Specification (operational PRD) |
| **System** | forge-auditAgent — Modular Agentic AI Environment |
| **Version** | 0.1 |
| **Status** | Active (living document) |
| **Owner** | forge-auditAgent maintainers / tech lead |
| **Last Updated** | 2026-08-03 |
| **Source PRD** | [PRD-AgenticAI-Modular.md](./PRD-AgenticAI-Modular.md) v1.0 |
| **Derivation** | This spec is a machine-parseable operational contract derived 1:1 from the source PRD. It does **not** add scope. Every requirement traces back to a source FR / NFR / acceptance criterion / validation scenario / constraint. |
| **Audience** | AI agents and engineers building against this system (construction phase), plus reviewers verifying implementation. |

## Living Document Contract

This is a **living document**. It is updated whenever the source PRD changes or whenever an implementation milestone completes. Update rules:

1. **When to update**
   - The source PRD (`PRD-AgenticAI-Modular.md`) is revised → re-derive affected sections and bump version.
   - A milestone is accepted against the **Validation & Acceptance** tables (§7.x in source) → mark affected requirements `[VERIFIED]` in the `Status` note of the Verification subsection, never in the requirement row itself.
   - An **open question** in this spec is resolved by a decision → resolve it in the source PRD first, then restate here.
2. **Versioning**: `vMAJOR.MINOR`. MAJOR bumps on scope changes (new/removed requirements); MINOR bumps on rephrasing, clarification, or verification updates.
3. **Changelog format**: every change MUST append a row to the [Change Log](#change-log) at the end:

   `YYYY-MM-DD — vX.Y — <one-line description of the change, and why>`

4. **Traceability invariant**: no requirement may exist in this document without a `Trace` reference to the source PRD. Any new requirement must first be added to the source PRD, then mirrored here.
5. **Unambiguous contract**: requirements are written so an AI builder can implement without asking clarifying questions. Where the source is genuinely silent on an edge case, the `Error/Edge behavior` column states `Not specified in source — implement fail-safe default` and the ambiguity is flagged in [Appendix: Ambiguities & Interpretations](#appendix-ambiguities--interpretations).

---

## How to Read This Spec

**Numbering scheme**

- Functional requirements use module prefixes: `CW-` (Construction Workbench), `AE-` (Audit Engine), `LO-` (LLM Orchestration), `LP-` (Loading & Parsing), `ER-` (Export & Reporting), `US-` (User & Session), `RT-` (Real-Time Progress), `DS-` (Docker Sandbox).
- NFRs keep their source IDs verbatim: `NFR-1.1` … `NFR-6.4`.
- Every row's `Trace` column points to the source FR, AC, validation scenario, or constraint it derives from.

**Priority semantics**

| Priority | Meaning |
|---|---|
| **Must** | Release-blocking. Failure to meet = system not accepted. |
| **Should** | Expected; may be deferred only with explicit owner sign-off and recorded in the Change Log. |
| **Could** | Optional / future. Implement only if time and architecture permit; never blocks acceptance. |

**When is a requirement DONE?**

A requirement is DONE when:
1. Its **Verification** procedure passes (deterministic checks are proven by automated tests with **no LLM call**; subjective checks are proven via **LLM-as-a-Judge** or human review as marked), and
2. Its acceptance criterion from the source PRD's §7 Validation & Acceptance tables is satisfied, and
3. It has no unresolved open question blocking it.

**How agents should consume this doc**

1. Read the module's **Purpose → Scope → Non-Goals** first to bound the work.
2. Implement every **Must/Should** row in the requirement table; treat **Could** as out of scope unless explicitly assigned.
3. Honor the **Error/Edge behavior** column — do not ask the user how to behave; the column defines the contract.
4. Prove completion with the **Verification** subsection. The verification column of each table classifies each check as `no LLM call` (deterministic) or `LLM-as-a-Judge` (subjective) where applicable.
5. Never cross a **Non-Goal** boundary even if it seems convenient.

---

## 1. Notebook Construction Workbench

**Source section:** PRD §4.1 (FR-1.1–FR-1.4), validation §7.1.

### Purpose

Provide a guided, three-phase authoring workflow (Scaffold → Write → Validate During Writing) that turns a blank notebook into a well-structured, reproducible Jupyter `.ipynb` from the start. The workbench embeds structural templates, reproducibility controls, and incremental validation gates so the author never has to rely on individual discipline to produce a reviewable notebook.

### Scope

Must scaffold notebooks from canonical section templates, collect reproducibility configuration (seeds, deterministic flags, device config, dependency file location), validate incrementally as sections are written, and enforce a single versioned output/artifact routing convention.

### Non-Goals

- Is NOT a notebook IDE or a replacement for JupyterLab / VS Code (source §2.3: "the system reads existing notebooks for audit; construction is a guided workflow, not a notebook replacement").
- Does NOT support real-time collaborative editing.
- Does NOT train ML models or track experiments (that is the audited notebook's job, not the platform's).
- Does NOT transpile notebooks to scripts or run deployment pipelines (deployment is audit *recommendations* only).
- Does NOT validate the full notebook end-to-end; incremental validation covers sections written so far, and the author may override it.

### Requirements

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| CW-1.1 | The workbench SHALL present the eight canonical section headers as an interactive template: Environment & Dependencies, Configuration & Global Parameters, Data Ingestion, Preprocessing & Feature Engineering, Model Definition & Training, Evaluation & Metrics, Artifact Export, Conclusions & Next Steps. | Must | If the template cannot be rendered (e.g., config read failure), show a descriptive error and abort scaffolding; do not generate a partial template. | FR-1.1 |
| CW-1.2 | The workbench SHALL generate a valid `.ipynb` file whose code/markdown cells place all eight canonical section headers as markdown cells in the exact canonical order. | Must | Generation MUST fail with a descriptive error rather than produce a non-`.ipynb` or out-of-order file. | FR-1.1 / AC1.1.1 |
| CW-1.3 | Each generated section SHALL include a brief placeholder markdown description of its purpose. | Must | A section removed by the user MUST NOT leave a dangling placeholder reference. | FR-1.1 / AC1.1.2 |
| CW-1.4 | Before finalising, the user SHALL be able to customise, reorder, or remove any section. | Must | Reordering MUST NOT break the `.ipynb` validity; a scaffold with zero remaining sections is permitted only if the user explicitly removes all. | FR-1.1 / AC1.1.3 |
| CW-1.5 | The generated scaffold SHALL create a `requirements.txt` or `environment.yml` placeholder cell inside the Environment section. | Must | If both placeholders are absent after generation, treat as generation failure. | FR-1.1 / AC1.1.4 |
| CW-2.1 | The reproducibility configuration wizard SHALL collect random seed values for numpy, torch, random, and sklearn. | Must | Wizard SHALL reject non-integer or empty seed input with an inline validation message; user may decline to set a seed (flag it as a known gap). | FR-1.2 / AC1.2.1 |
| CW-2.2 | Generated notebook cells SHALL pin the configured seeds (and deterministic flags / device configuration) before any stochastic operation in the notebook. | Must | If a seed is unset, the generated cell MUST NOT silently inject a fabricated value — it is omitted and the omission is surfaced. | FR-1.2 / AC1.2.2 |
| CW-2.3 | The dependency file path (`requirements.txt` / `conda.yaml` / `pyproject.toml`) SHALL be recorded in the notebook metadata. | Must | A non-existent dependency path is recorded as-is; existence is validated later by the audit engine (Pass 2), not here. | FR-1.2 / AC1.2.3 |
| CW-3.1 | The workbench SHALL detect when a new section header cell has been added and prompt the author to validate the notebook up to that point. | Should | Detection runs on cell edits; on detection failure, the prompt is skipped but a log entry is written — the author is never blocked from writing. | FR-1.3 / AC1.3.1 |
| CW-3.2 | Incremental validation SHALL perform a kernel restart, a full re-execution of all cells up to that point, and a comparison of outputs against previously captured snapshots. | Should | If the kernel fails to start, report the failure with the kernel error and do not auto-retry more than once. | FR-1.3 / AC1.3.2 |
| CW-3.3 | Cell idempotency violations SHALL be flagged with the cell index and an expected-vs-actual output summary. | Should | A cell that has no prior snapshot is compared on first-run behaviour only; it is not a violation. | FR-1.3 / AC1.3.3 |
| CW-3.4 | The author SHALL be able to dismiss the validation prompt and continue writing (explicit override), with the override recorded. | Should | Dismissal only skips the prompt for the current section; the next new section header re-arms it. | FR-1.3 / AC1.3.4 |
| CW-4.1 | At scaffold time the workbench SHALL collect an output root from the user (default `./output/`). | Should | A relative root is resolved against the notebook's directory; an absolute root outside the workspace is permitted but flagged at scaffold time. | FR-1.4 / AC1.4.1 |
| CW-4.2 | Artifact export cells SHALL be checked so that writable paths fall under the configured output root. | Should | Path traversal attempts (`..`, absolute paths escaping the root) MUST be rejected/flagged, not executed. | FR-1.4 / AC1.4.2 |
| CW-4.3 | Ad-hoc writes to paths outside the output root SHALL be flagged as findings. | Should | Flagging is detection-only at write time; it MUST NOT silently rewrite the user's code. | FR-1.4 / AC1.4.3 |

### Verification

Each acceptance criterion is proven as follows (source §7.1 + §7.9 end-to-end):

| Verification | Method | Requirement(s) | LLM involved |
|---|---|---|---|
| Scaffold wizard produces `.ipynb` with all eight headers, placeholders, and env placeholder | Launch wizard, select all eight sections, assert on generated file structure | CW-1.1–CW-1.5 | no LLM call |
| Seed pinning + dependency declaration in generated cells | Create notebook via wizard; assert generated cell text and notebook metadata | CW-2.1–CW-2.3 | no LLM call |
| Incremental validation restarts kernel and re-executes | Complete one section, trigger validation, assert kernel restart and clean re-execution | CW-3.1–CW-3.4 | no LLM call (idempotency comparison is deterministic) |
| Artifact routing enforcement | Write a cell saving outside the output root; assert it is flagged | CW-4.1–CW-4.3 | no LLM call |

E2E hook: §7.9 steps 2–4 exercise scaffold, reproducibility config, and incremental validation.

### Open Questions

- **OW-1 (FR-1.3):** The source does not define how the *first* validation snapshot is established (there is no "previously captured snapshot" for a brand-new section). Interpretation: the first validation run captures the snapshot; subsequent runs compare. Implementer should confirm.
- **OW-2 (FR-1.3):** "Output correctness" is not defined quantitatively for non-numeric outputs (markdown, figures). Interpretation: use the same deterministic comparison primitives as the sandbox output comparison (FR-8.2) where applicable.

---

## 2. Notebook Audit Engine — Six Passes

**Source section:** PRD §4.2 (FR-2.1–FR-2.8), §4.3 levels (FR-3.4), validation §7.2, §7.9.

### Purpose

Execute a systematic, repeatable six-pass review protocol over a loaded notebook: Structural Overview, Reproducibility, Data Integrity, ML Correctness, Code Quality, Deployment Readiness. The passes are grouped into three conceptual levels — Conceptual (Passes 1–2), Methodological (Passes 3–4), Implementation (Passes 5–6) — with interactive gate decisions between levels and the ability to scope the audit to specific focus areas.

### Scope

Map structure and red flags (Pass 1); verify reproducibility controls (Pass 2); review data pipeline integrity (Pass 3); audit ML methodology (Pass 4); review code quality (Pass 5); assess deployment readiness (Pass 6); support scoped execution; expose gate decision points between levels.

### Non-Goals

- Does NOT edit or fix the notebook — it only reports findings and scores.
- Does NOT validate/execute the notebook itself here (execution happens via the deterministic verification engine, §LO-2.3, and the Docker sandbox, Module 8).
- Does NOT provide a human peer-review workflow; the human role is limited to gate decisions (FR-2.8) and optional human review (FR-3.5).
- Does NOT replace MLflow / Weights & Biases for training or experiment tracking.
- Pass scoring is three-valued only (Low / Moderate / High); no finer gradation is defined.

### Requirements

**Pass 1 — Structural Overview (FR-2.1)**

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| AE-1.1 | Pass 1 SHALL produce a section map listing all markdown headers with their line numbers. | Must | A notebook with zero markdown headers produces an empty section map (not an error) and this is reported. | FR-2.1 / AC2.1.1 |
| AE-1.2 | Pass 1 SHALL flag cells with out-of-order execution counts or hidden dependencies. | Must | Cells with no execution count are treated as "not executed" and listed, not crash the pass. | FR-2.1 / AC2.1.2 |
| AE-1.3 | Pass 1 SHALL list preliminary red flags (missing outputs, broken imports, orphaned cells) with cell references. | Must | A broken import is detected statically where possible; if undetectable without execution, it is deferred to execution passes. | FR-2.1 / AC2.1.3 |
| AE-1.4 | Pass 1 SHALL record the user-specified focus-area scope as part of its deliverable. | Must | With no focus areas supplied, scope is "full audit" and this is recorded explicitly. | FR-2.1 / AC2.1.4 |

**Pass 2 — Reproducibility Check (FR-2.2)**

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| AE-2.1 | Pass 2 SHALL verify the presence of `requirements.txt`, `conda.yaml`, or `pyproject.toml` and that declared versions are pinned (exact versions, not ranges). | Must | A missing dependency file is flagged as a finding; absence does not abort the pass. Ranges (`>=`, `~=`) count as unpinned. | FR-2.2 / AC2.2.1 |
| AE-2.2 | Pass 2 SHALL check that global seeds (numpy, torch, random, sklearn) are set before any stochastic operation. | Must | Stochastic operations are identified per the module's static heuristics; an undetected stochastic op is a coverage limitation, not a false pass. | FR-2.2 / AC2.2.2 |
| AE-2.3 | Pass 2 SHALL flag absolute file paths, environment variables, API keys, or credentials in the notebook. | Must | Detection is content-based; a flagged credential is reported with cell reference but the raw value MUST NOT be echoed in the report. | FR-2.2 / AC2.2.3 / NFR-4.3 |
| AE-2.4 | Pass 2 SHALL output a Reproducibility risk score of Low, Moderate, or High. | Must | Scoring rule set must be deterministic and reproducible across runs of the same input. | FR-2.2 / AC2.2.4 |

**Pass 3 — Data Integrity Review (FR-2.3)**

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| AE-3.1 | Pass 3 SHALL identify the train/test split cell and confirm it precedes preprocessing. | Must | No train/test split found → reported as "no data pipeline present" and the pass continues (per §7.9 step 7c). | FR-2.3 / AC2.3.1 |
| AE-3.2 | Pass 3 SHALL flag any scaler, encoder, or imputer fitted on the full dataset (data leakage). | Must | Fit calls are traced to their input scope; where scope is ambiguous, flag with "possible" severity rather than certainty. | FR-2.3 / AC2.3.2 |
| AE-3.3 | Pass 3 SHALL check that the missing-data strategy is fit on training data only. | Must | If strategy fit scope cannot be determined, flag as unresolved with cell reference. | FR-2.3 / AC2.3.3 |
| AE-3.4 | Pass 3 SHALL flag missing dtype or shape validation at data ingestion. | Must | Applies only when an ingestion step is present. | FR-2.3 / AC2.3.4 |
| AE-3.5 | Pass 3 SHALL output a data pipeline integrity report. | Must | Report is produced even when no data pipeline exists (explicit "none detected" section). | FR-2.3 / AC2.3.5 |

**Pass 4 — ML Correctness Audit (FR-2.4)**

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| AE-4.1 | Pass 4 SHALL flag inappropriate evaluation metrics (e.g., accuracy on imbalanced classification). | Must | Applies only when an ML evaluation exists; no ML section → report "no ML section present for scoring" (§7.9 step 7d). | FR-2.4 / AC2.4.1 |
| AE-4.2 | Pass 4 SHALL verify cross-validation folds preserve train/test separation. | Must | Use of `StratifiedKFold`/`KFold` vs full-data preprocessing is compared; leakage patterns are flagged. | FR-2.4 / AC2.4.2 |
| AE-4.3 | Pass 4 SHALL confirm hyperparameter tuning uses validation data only. | Must | Tuning that touches test data is flagged as High severity. | FR-2.4 / AC2.4.3 |
| AE-4.4 | Pass 4 SHALL flag a missing baseline comparison. | Must | "Baseline" is interpreted as any simple reference model or heuristic; absence is a finding, presence is pass. | FR-2.4 / AC2.4.4 |
| AE-4.5 | Pass 4 SHALL output an ML correctness checklist. | Must | Checklist is generated even when the notebook has no ML content (all items marked N/A). | FR-2.4 / AC2.4.5 |

**Pass 5 — Code Quality Review (FR-2.5)**

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| AE-5.1 | Pass 5 SHALL identify code patterns repeated across three or more cells as refactoring candidates. | Must | Repetition is detected by normalized code similarity; near-duplicates with minor variable differences count. | FR-2.5 / AC2.5.1 |
| AE-5.2 | Pass 5 SHALL flag unused imports and dead code paths. | Must | Static analysis is used; false negatives are acceptable, false positives SHOULD be avoided. | FR-2.5 / AC2.5.2 |
| AE-5.3 | Pass 5 SHALL flag non-descriptive variable names (e.g., `df1`, `tmp`, `x2`). | Must | Only assignment targets are considered; standard loop/iteration variables are exempt. | FR-2.5 / AC2.5.3 |
| AE-5.4 | Pass 5 SHALL flag large cell outputs without truncation (bloated dataframe printing, raw tensor dumps). | Must | Threshold for "large" is a module configuration value; default behavior flags any output exceeding the threshold. | FR-2.5 / AC2.5.4 |
| AE-5.5 | Pass 5 SHALL output a code quality and smell report. | Must | Report generated even for a notebook with zero findings. | FR-2.5 / AC2.5.5 |

**Pass 6 — Deployment Readiness (FR-2.6)**

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| AE-6.1 | Pass 6 SHALL verify model/plot/report artifacts are saved with versioned or timestamped filenames. | Must | Untracked/overwritten filenames are flagged; absence of any artifact export is a finding. | FR-2.6 / AC2.6.1 |
| AE-6.2 | Pass 6 SHALL check that inference logic is separable from training. | Must | If separation cannot be assessed statically, flag as "not verifiable" rather than pass. | FR-2.6 / AC2.6.2 |
| AE-6.3 | Pass 6 SHALL flag missing compute/memory resource documentation. | Must | Absence of a documented resource section is the finding; content of the section is not scored. | FR-2.6 / AC2.6.3 |
| AE-6.4 | Pass 6 SHALL confirm the environment export is present and up to date. | Must | "Up to date" is checked against imports found in code cells; a mismatch is flagged. | FR-2.6 / AC2.6.4 |
| AE-6.5 | Pass 6 SHALL flag any PII or credentials visible in notebook source, by default. | Must | Scans email addresses, API keys, and file paths by default (NFR-4.4). Raw values MUST NOT be echoed in the report. | FR-2.6 / AC2.6.5 / NFR-4.4 |
| AE-6.6 | Pass 6 SHALL output a Deployment Readiness score of Low, Moderate, or High. | Must | Scoring rule set deterministic and reproducible. | FR-2.6 / AC2.6.6 |

**Scoped Audit Execution (FR-2.7)**

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| AE-7.1 | The system SHALL accept a user-provided list of focus area labels (e.g., `["data leakage", "code style"]`). | Must | Unknown labels are rejected with an explicit list of valid labels; they are not silently ignored. | FR-2.7 / AC2.7.1 |
| AE-7.2 | Only passes matching the focus areas SHALL execute, plus Pass 1 (always runs to establish scope context). | Must | Empty focus list = full audit; every supplied label maps to exactly one pass (or is rejected). | FR-2.7 / AC2.7.2 |
| AE-7.3 | Skipped passes SHALL be marked with status `skipped` in the report. | Must | `skipped` is distinct from `passed`, `flagged`, and `error` in the `PassResult.status` enum. | FR-2.7 / AC2.7.3 |

Validation: §7.2 "Scoped audit" scenario — focus areas `["data leakage", "code quality"]` must execute only Pass 1, Pass 3, Pass 5; others `skipped`.

**Gate Decisions Between Levels (FR-2.8)**

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| AE-8.1 | After Level 1 completes, the system SHALL show a gate prompt when Reproducibility risk is High. | Should | Gate prompt only triggers on the specified condition; Low/Moderate reproducibility proceeds without a prompt. | FR-2.8 / AC2.8.1 |
| AE-8.2 | At the gate, the user SHALL choose exactly one of: `stop and flag`, `continue to Level 2`, or `escalate to human reviewer`. | Should | No default action is taken; the gate blocks Level 2 until a choice is recorded. | FR-2.8 / AC2.8.2 |
| AE-8.3 | The gate decision and its rationale SHALL be recorded in the audit report. | Should | If the user supplies no rationale, record the decision with `rationale: null`. | FR-2.8 / AC2.8.3 |

Validation: §7.2 "Gate decision interaction" — Level 1 on a failing notebook shows the prompt; choosing `continue` runs Level 2. Also exercised in §7.9 step 8.

### Verification

| Verification | Method | Requirement(s) | LLM involved |
|---|---|---|---|
| Full six-pass audit | Submit a notebook with deliberate issues (missing seeds, data leakage, repetitive code, hardcoded paths); assert all six passes produce findings | AE-1.1–AE-6.6 | Mixed: objective checks = **no LLM call**; subjective checks (naming, documentation, methodology) = **LLM-as-a-Judge** |
| Scoped audit | Focus areas `["data leakage", "code quality"]` → only Passes 1, 3, 5 execute; others `skipped` | AE-7.1–AE-7.3 | no LLM call for pass selection |
| Gate decision interaction | High-risk notebook → prompt appears; `continue` → Level 2 runs; decision recorded | AE-8.1–AE-8.3 | no LLM call |
| E2E happy path | §7.9 steps 5–8 | AE-1.x–AE-8.x | Mixed |

Note on deterministic vs subjective mapping (source §7.3): dependency resolution, file existence, execution verification, and output comparison are deterministic (**no LLM call**). Documentation quality, methodological coherence, code naming, and output hygiene are **LLM-as-a-Judge**.

### Open Questions

- **OW-3 (FR-2.8):** The source defines the gate prompt trigger only for *High Risk* reproducibility at *Level 1*. It does not define triggers for gates at Level 2→3, nor behavior for Moderate risk. Interpretation: apply the same rule (gate on High risk within the just-completed level) at each boundary, and treat Moderate as "proceed without prompt." Confirm with owner.

---

## 3. LLM Orchestration — Provider-Agnostic, Three-Level Audit

**Source section:** PRD §4.3 (FR-3.1–FR-3.5), validation §7.3.

### Purpose

Decouple all LLM judgment from any single vendor by abstracting inference behind a common provider interface, and separate deterministic (rule-based) checks from LLM-as-a-Judge evaluations so that objective facts are never subject to model variance. It also enforces the three-level audit execution order with optional human-in-the-loop gates.

### Scope

Provider abstraction interface with pluggable registrations, a deterministic verification engine for objective checks, LLM-as-a-Judge prompt/parse handling for subjective passes, ordered three-level execution, and optional human review at gates.

### Non-Goals

- Does NOT implement model training, fine-tuning, or embedding store management.
- Does NOT send notebook content anywhere unless the user explicitly configured and selected a cloud provider (source §6.4).
- Does NOT define audit *policy* (which checks run) — that is the Audit Engine's job; orchestration only executes it.
- Does NOT decide which provider is best; provider selection is user configuration.

### Requirements

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| LO-1.1 | The system SHALL expose a common `LLMProvider` interface (abstract base class or `typing.Protocol`) with methods `chat_completion()`, `stream_chat()`, and `embed()`. | Must | Implementations failing to provide all three methods MUST fail at registration time, not at call time. | FR-3.1 / AC3.1.1 |
| LO-1.2 | The system SHALL ship at least three implementations: `OllamaProvider`, `LlamaCppProvider`, and `OpenAIProvider`. | Must | Each implementation isolates provider-specific SDK calls behind the interface. | FR-3.1 / AC3.1.2 |
| LO-1.3 | New providers SHALL be registrable via a plugin registry without modifying existing provider or audit code. | Must | Registration is idempotent; a duplicate registration returns a clear error or no-op, not a crash. | FR-3.1 / AC3.1.3 |
| LO-1.4 | Provider selection SHALL be configurable at runtime without service restart. | Must | Switching providers mid-run applies to the next LLM invocation; in-flight requests complete on the original provider. | FR-3.1 / AC3.1.4 |
| LO-2.1 | Dependency checks SHALL parse `requirements.txt` / `conda.yaml` for version pins using rule-based logic — **no LLM call**. | Must | If the file cannot be parsed, the check returns "unverifiable" and passes the file to the LLM pass only if the level template requires it. | FR-3.2 / AC3.2.1 |
| LO-2.2 | File existence checks SHALL use OS filesystem APIs — **no LLM call**. | Must | Permission errors are reported as errors, not as "file missing". | FR-3.2 / AC3.2.2 |
| LO-2.3 | Execution verification SHALL run the notebook (or selected cells) in a sandbox and capture exit codes — **no LLM call**. | Must | Sandbox failure (Docker unavailable) falls back per Module 8 (DS-1.5) with a warning. | FR-3.2 / AC3.2.3 / FR-8.1 |
| LO-2.4 | The system SHALL combine deterministic results and LLM-judged results into the final report. | Must | Each finding records its provenance: `deterministic` vs `llm_judge`. | FR-3.2 / AC3.2.4 |
| LO-3.1 | Each audit level (Conceptual, Methodological, Implementation) SHALL have a corresponding LLM prompt template. | Must | A missing or invalid template is a configuration error surfaced at startup, not silently ignored. | FR-3.3 / AC3.3.1 |
| LO-3.2 | The system SHALL parse the LLM response into a list of `Finding` objects with severity, cell index, and message. | Must | Parsing MUST be lenient to schema drift; see LO-3.3 for failure handling. | FR-3.3 / AC3.3.2 |
| LO-3.3 | Parsing errors or malformed LLM responses SHALL be handled gracefully with a fallback pass result. | Must | Fallback MUST NOT crash the pipeline; the pass is marked `error` with the raw response retained in metadata and a finding "LLM output unparseable" added. | FR-3.3 / AC3.3.3 |
| LO-3.4 | The exact prompt sent and the raw LLM response SHALL be logged in the audit report metadata for transparency. | Must | This applies by default; redaction of credentials/PII from the log is applied where the content is flagged (NFR-4.4). | FR-3.3 / AC3.3.4 |
| LO-4.1 | The system SHALL execute Level 1 (Passes 1–2) first, always. | Must | Level 1 is never skipped, even in scoped audits (Pass 1 is mandatory). | FR-3.4 / AC3.4.1 |
| LO-4.2 | Level 2 SHALL begin only after Level 1 completes and any applicable gate is resolved. | Must | A blocked gate (no decision recorded) MUST halt the pipeline. | FR-3.4 / AC3.4.2 |
| LO-4.3 | Level 3 SHALL begin only after Level 2 completes and any applicable gate is resolved. | Must | A blocked gate MUST halt the pipeline. | FR-3.4 / AC3.4.3 |
| LO-4.4 | Each level SHALL produce its own deliverable subset of the final report. | Must | If a level is not reached (gate stop), the final report still contains completed levels' deliverables and marks the rest `skipped`. | FR-3.4 / AC3.4.4 |
| LO-5.1 | Each gate SHALL present a summary of findings from the completed level for human review. | Could | Summary is derived from the level's deliverables; no LLM re-synthesis required. | FR-3.5 / AC3.5.1 |
| LO-5.2 | The human reviewer SHALL be able to approve, reject with reason, or request modifications. | Could | Rejection or modification-request MUST halt progression to the next level until resolved. | FR-3.5 / AC3.5.2 |
| LO-5.3 | The reviewer's decision and notes SHALL be recorded in the audit report. | Could | Decision is immutable once recorded; corrections create a new audit run. | FR-3.5 / AC3.5.3 |

### Verification

| Verification | Method | Requirement(s) | LLM involved |
|---|---|---|---|
| Provider abstraction | Run LLM-judged passes on Ollama; switch to llama.cpp; run same notebook; assert structurally identical results | LO-1.1–LO-1.4 | LLM-as-a-Judge |
| Deterministic vs LLM separation | Notebook with pinned deps (deterministic) + poor docs (LLM); assert deterministic findings appear with **no LLM call** (instrument/no-network condition) | LO-2.1–LO-2.4 | no LLM call |
| Structured prompt parsing | Send known notebook to Level 1 prompt; assert response parses into valid `Finding` objects with correct severity and cell refs | LO-3.1–LO-3.4 | LLM-as-a-Judge + deterministic parse assertions |
| Three-level execution order | Full audit: assert Level 1 → Level 2 → Level 3 ordering and gate resolution between levels | LO-4.1–LO-4.4 | no LLM call |
| Human-in-the-loop gate | At gate, approve / reject-with-reason / request-modifications; assert recording and blocking | LO-5.1–LO-5.3 | no LLM call |

Source validation mapping: §7.3 scenarios map 1:1 to the rows above.

### Open Questions

- **OW-4 (FR-3.3):** The source specifies a "fallback pass result" for malformed LLM responses but does not define its exact shape. Interpretation: status `error`, zero findings, raw response in metadata, one synthetic `info` finding. Confirm.
- **OW-5 (FR-3.1):** `embed()` is required on the interface but the PRD never specifies a consumer of embeddings. Interpretation: implement the method as part of the contract; no pipeline consumer in this iteration. Flagged for traceability.

---

## 4. Notebook Loading & Parsing

**Source section:** PRD §4.4 (FR-4.1–FR-4.3), constraints §6.3, validation §7.4.

### Purpose

Turn any valid Jupyter `.ipynb` (v4.x) — from disk or a GitHub raw URL — into the internal `Notebook` data model that all audit passes consume, validating structure on load so downstream passes never see malformed input.

### Scope

Local `.ipynb` parsing, GitHub raw URL fetching with ephemeral caching, and load-time structural validation (schema, cell types, execution count ordering, non-empty).

### Non-Goals

- Does NOT support notebook formats other than Jupyter `.ipynb` v4.x (R Markdown, Quarto, Google Colab `.ipynb` without output, Zeppelin are out of scope — §6.3).
- Does NOT persist downloaded remote notebooks (ephemeral cache only, FR-4.2).
- Does NOT execute any cells during loading; execution is the sandbox module's job.
- Non-Python kernels (R, Julia) parse but Python-specific audit patterns get reduced coverage — coverage, not failure (§6.3).

### Requirements

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| LP-1.1 | The system SHALL load and parse any valid `.ipynb` file (format v4 or v4.x). | Must | A version header other than v4.x is rejected with a descriptive validation error. | FR-4.1 / AC4.1.1 |
| LP-1.2 | The system SHALL extract and categorise cells as `code` or `markdown`. | Must | Unknown cell types are categorised per FR-4.3 (warning, not abort). | FR-4.1 / AC4.1.2 |
| LP-1.3 | The system SHALL preserve execution counts, cell metadata, and output data in the `Notebook` model. | Must | Missing optional fields (e.g., no output) are preserved as absent, not dropped silently. | FR-4.1 / AC4.1.3 |
| LP-1.4 | Invalid or corrupt `.ipynb` files SHALL produce a descriptive validation error. | Must | The error includes the cause (unparseable JSON, missing field, wrong schema) — never a bare stack trace. | FR-4.1 / AC4.1.4 |
| LP-2.1 | The system SHALL accept a GitHub raw URL matching `https://raw.githubusercontent.com/.../*.ipynb`. | Must | URLs outside this pattern are rejected with an actionable message (accepted pattern shown). | FR-4.2 / AC4.2.1 |
| LP-2.2 | The system SHALL download the notebook and cache it temporarily (ephemeral, not persisted). | Must | The cached file is removed after the session/import completes; it never lands in audit history. | FR-4.2 / AC4.2.2 |
| LP-2.3 | Download errors (HTTP 404, timeout, invalid URL) SHALL be reported with actionable messages. | Must | Timeout and 404 are distinct error types; a retry is attempted once for transient failures. | FR-4.2 / AC4.2.3 |
| LP-2.4 | A URL-loaded notebook SHALL be indistinguishable from a locally loaded notebook in downstream passes. | Must | The `Notebook` model carries no "remote vs local" provenance that alters pass behavior. | FR-4.2 / AC4.2.4 |
| LP-3.1 | On load, the system SHALL validate the notebook against the Jupyter JSON schema and reject malformed files. | Must | Rejection produces the descriptive error from LP-1.4. | FR-4.3 / AC4.3.1 |
| LP-3.2 | Unknown or invalid cell types SHALL produce warnings but SHALL NOT abort loading. | Must | Warning includes cell index; the unknown cell is preserved as opaque in the model. | FR-4.3 / AC4.3.2 |
| LP-3.3 | Non-linear or reset execution counts SHALL be flagged as findings. | Must | Flagging happens at load; findings feed Pass 1 (AE-1.2). | FR-4.3 / AC4.3.3 |
| LP-3.4 | Empty notebooks (zero cells) SHALL produce a validation error. | Must | The error message states the notebook has no cells. | FR-4.3 / AC4.3.4 |

### Verification

| Verification | Method | Requirement(s) | LLM involved |
|---|---|---|---|
| Local `.ipynb` load | Load a valid mixed code/markdown notebook; assert cell parse + execution-count preservation | LP-1.1–LP-1.4 | no LLM call |
| GitHub URL load | Load from a raw GitHub URL; assert identical parse to local load | LP-2.1–LP-2.4 | no LLM call |
| Corrupt file handling | Submit malformed JSON as `.ipynb`; assert descriptive error and graceful failure | LP-3.1, LP-1.4 | no LLM call |

Source validation mapping: §7.4 scenarios map 1:1 to the rows above. E2E §7.9 step 5 loads a notebook into the Audit Engine.

### Open Questions

None — the source is unambiguous for this module.

---

## 5. Export & Reporting

**Source section:** PRD §4.5 (FR-5.1–FR-5.4), validation §7.5.

### Purpose

Turn the in-memory `AuditReport` into durable, shareable artifacts: a structured JSON contract for machines, a human-readable Markdown report for PRs/supplementary materials, and a print-ready PDF for academic/formal submission — plus a per-notebook run history enabling comparison over time.

### Scope

JSON export with versioned schema and re-import, Markdown report generation with risk indicators and severity badges, PDF generation without external LaTeX, and chronological audit-run versioning/comparison.

### Non-Goals

- Does NOT render the notebook itself — it renders the *audit* of the notebook.
- Does NOT support formats other than JSON / Markdown / PDF in this iteration.
- Does NOT handle report distribution (email, publishing) — export only.
- PDF re-import is NOT required (only JSON re-imports, FR-5.1).

### Requirements

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| ER-1.1 | The system SHALL export the full audit report as a structured JSON file containing all pass results, findings, scores, and metadata. | Must | The export MUST include every field of the `AuditReport` and `PassResult` models; no field may be elided. | FR-5.1 / AC5.1.1 |
| ER-1.2 | Exported findings SHALL include severity, cell index, category, and message. | Must | Findings missing any of the four attributes fail export validation. | FR-5.1 / AC5.1.2 |
| ER-1.3 | The JSON schema SHALL be versioned and documented. | Must | Export embeds `schema_version`; the versioned schema doc ships with the module. | FR-5.1 / AC5.1.3 |
| ER-1.4 | Exported JSON SHALL be re-importable for viewing or comparison. | Must | Re-import of a previously exported JSON MUST reproduce an identical in-memory report (round-trip test). | FR-5.1 / AC5.1.4 |
| ER-2.1 | The Markdown report SHALL include notebook identity, overall status, and pass-by-pass findings. | Must | A run that halted at a gate still produces a report containing completed levels. | FR-5.2 / AC5.2.1 |
| ER-2.2 | Risk scores in Markdown SHALL use the visual indicators Low = ✅, Moderate = ⚠️, High = 🚫. | Must | Unknown/absent scores render as a neutral marker, not an empty cell. | FR-5.2 / AC5.2.2 |
| ER-2.3 | Each finding SHALL be listed with its cell reference and severity badge. | Must | Findings without a cell reference (notebook-level) render with a `—` reference placeholder. | FR-5.2 / AC5.2.3 |
| ER-2.4 | Gate decisions, if recorded, SHALL be included as a timeline section. | Must | No gate decisions → section omitted entirely (not rendered empty). | FR-5.2 / AC5.2.4 |
| ER-3.1 | The PDF report SHALL include a title page with notebook name, timestamp, and overall score. | Must | Missing notebook name falls back to the filename; timestamp is UTC ISO-8601. | FR-5.3 / AC5.3.1 |
| ER-3.2 | Pass-level results in the PDF SHALL be paginated with clear section headings. | Must | A pass with many findings spans pages; headings repeat on continuation pages. | FR-5.3 / AC5.3.2 |
| ER-3.3 | Risk scores in the PDF SHALL be rendered as color-coded badges. | Must | Color is secondary — the score text must also be distinguishable in grayscale (accessibility). | FR-5.3 / AC5.3.3 |
| ER-3.4 | PDF generation SHALL use a pure-Python PDF library and SHALL NOT require external LaTeX installation. | Must | On environments without the PDF library, generation fails with an actionable install message. | FR-5.3 / AC5.3.4 |
| ER-4.1 | Each audit run SHALL be timestamped and stored with a unique run ID. | Must | Run IDs are unique per notebook history; timestamp collisions are disambiguated by the ID. | FR-5.4 / AC5.4.1 |
| ER-4.2 | The user SHALL be able to view a list of past audit runs for a given notebook. | Must | History listing works per notebook identity; ordering is newest-first. | FR-5.4 / AC5.4.2 |
| ER-4.3 | The user SHALL be able to compare two runs side-by-side, showing score deltas and new/resolved findings. | Could | Deltas are computed per pass; a finding is "new" if present in the later run only, "resolved" if present in the earlier run only. | FR-5.4 / AC5.4.3 |

### Verification

| Verification | Method | Requirement(s) | LLM involved |
|---|---|---|---|
| JSON export / re-import round-trip | Run audit, export JSON, re-import; assert all fields match the in-memory report | ER-1.1–ER-1.4 | no LLM call |
| Markdown export | Run audit, export MD; assert readable output with scores, findings, cell references | ER-2.1–ER-2.4 | no LLM call |
| PDF export | Run audit, export PDF; assert title page and paginated passes, no LaTeX dependency | ER-3.1–ER-3.4 | no LLM call |

Source validation mapping: §7.5 scenarios map 1:1. E2E §7.9 steps 9–10 export JSON/MD/PDF and re-import JSON.

### Open Questions

None — the source is unambiguous for this module.

---

## 6. User & Session Management

**Source section:** PRD §4.6 (FR-6.1–FR-6.3), validation §7.6.

### Purpose

Provide two operational modes cleanly: a local, authentication-free desktop session that persists user configuration and audit history, and a future full-stack mode with JWT authentication and role-based access control. Local mode must never require auth; cloud/multi-user features must.

### Scope

Persistent local sessions (`~/.test-prompts/config.json` + local audit history), full-stack registration/login/RBAC, and authentication-free local operation with auth gating only for cloud/multi-user features.

### Non-Goals

- Does NOT implement multi-tenancy, team dashboards, or shared history in the desktop (local) iteration.
- Does NOT implement password reset, OAuth, or SSO (only registration + JWT login are specified).
- Does NOT persist audit history in a database in the desktop version (JSON files); PostgreSQL is the full-stack target only (§6.1).
- Local-mode auth is never required; the desktop app has no login screen.

### Requirements

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| US-1.1 | The desktop application SHALL persist user configuration to `~/.test-prompts/config.json` (or the equivalent platform path). | Must | Config write failures are surfaced as non-fatal warnings; the app continues with in-memory defaults. | FR-6.1 / AC6.1.1 |
| US-1.2 | Audit history SHALL be stored locally as JSON files in the audit directory. | Must | History directory is created on demand; a corrupted history file is quarantined with a warning, not fatal. | FR-6.1 / AC6.1.2 |
| US-1.3 | On launch, the session SHALL restore provider selection, model path, and last-opened notebook. | Must | Missing or invalid stored values fall back to safe defaults; restore failure never blocks launch. | FR-6.1 / AC6.1.3 |
| US-1.4 | Configuration changes SHALL take effect immediately without restart. | Must | The running session re-reads config on change; in-flight operations finish on the old config. | FR-6.1 / AC6.1.4 |
| US-2.1 | Registration SHALL validate email uniqueness and password strength (minimum 8 characters, mixed case). | Must | Duplicate email → clear "already registered" error; weak password → explicit strength error; no account is created. | FR-6.2 / AC6.2.1 |
| US-2.2 | Login SHALL return a JWT access token with configurable expiry. | Must | Invalid credentials return HTTP 401 with a generic message (no user enumeration). | FR-6.2 / AC6.2.2 |
| US-2.3 | Tokens SHALL be validated on every protected API endpoint. | Must | Missing/invalid/expired token → HTTP 401; insufficient role → HTTP 403. | FR-6.2 / AC6.2.3 |
| US-2.4 | Role-based access SHALL enforce: `author` → Construction Workbench; `reviewer` → run audits; `admin` → manage users and system config; `viewer` → read-only access to reports. | Must | Any action outside a role's set is denied (403) regardless of object ownership. | FR-6.2 / AC6.2.4 |
| US-3.1 | The desktop application SHALL launch directly to the main workspace with no login screen. | Must | This holds even when cloud features are configured but unauthenticated. | FR-6.3 / AC6.3.1 |
| US-3.2 | All local features (loading notebooks, running audits, exporting reports) SHALL be available without authentication. | Must | No auth prompt may gate local operations. | FR-6.3 / AC6.3.2 |
| US-3.3 | Cloud features (shared history, remote provider calls via proxy) SHALL prompt for authentication on first use. | Must | Declining auth leaves cloud features disabled but local features fully functional. | FR-6.3 / AC6.3.3 |

### Verification

| Verification | Method | Requirement(s) | LLM involved |
|---|---|---|---|
| Local session persistence | Configure provider/model, restart app; assert settings restored | US-1.1–US-1.4 | no LLM call |
| Full-stack registration & login | Register, login, assert JWT; request protected endpoint without token → assert HTTP 401 | US-2.1–US-2.3 | no LLM call |
| RBAC | Exercise each role against the permission matrix; assert 403 on out-of-scope actions | US-2.4 | no LLM call |
| Local mode no auth | Launch desktop app; assert no login prompt and all local features reachable | US-3.1–US-3.3 | no LLM call |

Source validation mapping: §7.6 scenarios map 1:1 (full-stack rows apply only to the full-stack build).

### Open Questions

- **OW-6 (FR-6.2):** The source does not specify a refresh-token strategy, JWT expiry default, or logout/revocation semantics. Interpretation: implement configurable expiry with server-side revocation list for the full-stack iteration; confirm with owner before the full-stack milestone.

---

## 7. Real-Time Progress & Visualization

**Source section:** PRD §4.7 (FR-7.1–FR-7.3), validation §7.7.

### Purpose

Keep the user continuously informed while an audit runs: which pass is executing, completion percentage, partial findings as produced, and — after completion — an expandable pass-by-pass results view plus side-by-side report comparison.

### Scope

Real-time progress streaming (desktop callbacks; SSE for full-stack), per-pass result cards with expand/collapse, and a two-report comparison view with score deltas.

### Non-Goals

- Does NOT stream notebook cell execution output — only *audit* progress.
- Does NOT provide collaborative/multi-user live views in the desktop iteration.
- Comparison view is limited to two reports side-by-side (no N-way comparison).

### Requirements

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| RT-1.1 | The desktop app SHALL show a progress bar per pass with status text. | Must | A pass in `error` status renders as failed in the bar but the pipeline continues per RT-1.3. | FR-7.1 / AC7.1.1 |
| RT-1.2 | Each pass completion SHALL trigger a UI update with the score and finding count. | Must | Updates are pushed immediately on pass completion; ordering of events is preserved. | FR-7.1 / AC7.1.2 |
| RT-1.3 | Errors during a pass SHALL be displayed immediately without halting the pipeline. | Must | Error display is non-blocking; the pass is marked `error` and remaining passes continue. | FR-7.1 / AC7.1.3 |
| RT-1.4 | The full-stack version SHALL use SSE to stream progress events to the frontend. | Must | SSE connection loss mid-audit is detected and the client reconnects; the audit run continues server-side. | FR-7.1 / AC7.1.4 |
| RT-2.1 | Each pass result SHALL be shown as a distinct card with pass name, number, and score badge. | Must | Cards render for `passed`, `flagged`, and `skipped` statuses; `error` cards show the error. | FR-7.2 / AC7.2.1 |
| RT-2.2 | Findings in each card SHALL be listed with severity icon, cell reference, and message. | Must | A finding missing any of the three renders a placeholder, never a blank row. | FR-7.2 / AC7.2.2 |
| RT-2.3 | Users SHALL be able to expand and collapse individual pass details. | Must | Collapsed state preserves card header (score + count); expand is per-card, not global. | FR-7.2 / AC7.2.3 |
| RT-2.4 | The full deliverable text SHALL be available via an expansion toggle. | Must | Deliverables too large to render inline are truncated with a "show full" toggle. | FR-7.2 / AC7.2.4 |
| RT-3.1 | The comparison view SHALL show pass scores aligned on the same row. | Must | A pass present in only one report renders the other side as "—". | FR-7.3 / AC7.3.1 |
| RT-3.2 | Findings that are new, resolved, or unchanged SHALL be visually distinguished. | Must | Classification per ER-4.3 semantics (new = later only, resolved = earlier only, unchanged = both). | FR-7.3 / AC7.3.2 |
| RT-3.3 | Score deltas SHALL be computed and displayed per pass. | Must | Delta is `later − earlier`; identical scores show a neutral marker, not `0`. | FR-7.3 / AC7.3.3 |

### Verification

| Verification | Method | Requirement(s) | LLM involved |
|---|---|---|---|
| Progress updates | Run full audit on desktop; assert progress bar advances through each pass with status text | RT-1.1–RT-1.3 | no LLM call |
| SSE streaming | (Full-stack) Open audit page, trigger audit; assert SSE events arrive per pass with finding counts | RT-1.4 | no LLM call |
| Pass-by-pass display | Post-audit, assert distinct cards, severity icons, cell refs, expand/collapse, deliverable toggle | RT-2.1–RT-2.4 | no LLM call |
| Comparison view | Compare two runs; assert aligned scores, distinguished findings, deltas per pass | RT-3.1–RT-3.3 | no LLM call |

Source validation mapping: §7.7 scenarios map 1:1 (SSE row applies to full-stack only).

### Open Questions

None — the source is unambiguous for this module.

---

## 8. Docker Sandbox Execution

**Source section:** PRD §4.8 (FR-8.1–FR-8.3), NFR-4.2/NFR-4.5, validation §7.8.

### Purpose

Verify end-to-end re-executability of a notebook inside an isolated, ephemeral Docker container so host contamination is impossible, compare re-execution output to the stored outputs, and bound resource usage to prevent runaway execution.

### Scope

Sandboxed notebook execution from a configurable base image with declared dependencies, cell-level output comparison with configurable tolerance, and configurable memory/CPU/timeout limits.

### Non-Goals

- Does NOT run in Docker in the current desktop (Flet) build — notebooks run in-process there; the sandbox is a full-stack/future capability and a **Should** requirement (§6.5, NFR-3.4).
- Does NOT provide sandbox network access by default (`--network none` unless user opts in, NFR-4.5).
- Does NOT persist containers — containers are destroyed after execution (ephemeral).
- Does NOT grant the container host filesystem access beyond the explicitly mounted notebook and output directories (NFR-4.2).

### Requirements

| ID | Requirement | Priority | Error/Edge behavior | Trace |
|---|---|---|---|---|
| DS-1.1 | The sandbox SHALL create a container from a configurable base image with the notebook's declared dependencies installed. | Must* | Dependency install failure is captured as a pass error, not a container leak; the container is still destroyed. | FR-8.1 / AC8.1.1 |
| DS-1.2 | The notebook SHALL be copied into the container and executed via `jupyter nbconvert --execute`. | Must* | Execution failure (non-zero exit) is captured as an error finding; container is destroyed. | FR-8.1 / AC8.1.2 |
| DS-1.3 | Execution output SHALL be captured and compared to the original notebook's outputs. | Must* | Comparison is deterministic (**no LLM call**) and uses the semantics of DS-2.1–DS-2.4. | FR-8.1 / AC8.1.3 |
| DS-1.4 | The container SHALL be destroyed after execution (ephemeral). | Must* | Destruction is guaranteed on success, failure, timeout, and error paths. | FR-8.1 / AC8.1.4 |
| DS-1.5 | When Docker is unavailable, the system SHALL handle it gracefully: fall back to local execution with a warning. | Must* | The fallback is recorded in the report metadata; the user is warned that isolation is absent. | FR-8.1 / AC8.1.5 / NFR-3.4 |
| DS-2.1 | Outputs SHALL be compared at the cell level (text output, error messages, rich display data). | Should | Comparison covers the three classes named; unknown output types are compared best-effort. | FR-8.2 / AC8.2.1 |
| DS-2.2 | Numerical differences within a configurable tolerance SHALL NOT be flagged. | Should | Default tolerance is a module configuration value (source does not fix a number — see OW-8); only differences beyond tolerance are flagged. | FR-8.2 / AC8.2.2 |
| DS-2.3 | Missing outputs (cells that produced output originally but none on re-execution) SHALL be flagged. | Should | A cell that legitimately produces no output in both runs is not a discrepancy. | FR-8.2 / AC8.2.3 |
| DS-2.4 | New error outputs in re-execution SHALL be flagged as High severity. | Should | Errors present in both runs are reported per general comparison rules, not auto-High. | FR-8.2 / AC8.2.4 |
| DS-3.1 | Memory limit (default 4 GB) SHALL be enforced via Docker `--memory`. | Should | Exceeding the limit → container OOM-killed and a finding reported (§7.8 resource-limit scenario). | FR-8.3 / AC8.3.1 |
| DS-3.2 | CPU limit (default 2 cores) SHALL be enforced via Docker `--cpus`. | Should | Enforcement is at the Docker layer; no application-level throttling logic. | FR-8.3 / AC8.3.2 |
| DS-3.3 | Execution timeout (default 30 minutes) SHALL be enforced; exceeding it terminates the container. | Should | Termination is a kill, not a graceful stop; the finding reports "timeout". | FR-8.3 / AC8.3.3 |
| DS-3.4 | Resource limits SHALL be configurable in the sandbox settings. | Should | Invalid values (negative, absurd) are rejected at save time with a message. | FR-8.3 / AC8.3.4 |

\* DS-1.x rows carry the source's **Should** priority (FR-8.1 is Should in the source PRD). They are grouped under "Must\*" only to express that *within* an enabled sandbox run, the behavior is unconditional. The module-level priority remains **Should** (NFR-3.4).

### Verification

| Verification | Method | Requirement(s) | LLM involved |
|---|---|---|---|
| Sandbox execution | Execute a notebook with pinned deps in Docker; assert container created → run → outputs captured → destroyed | DS-1.1–DS-1.5 | no LLM call |
| Output comparison | Re-execution with slightly different numeric output; assert within-tolerance not flagged, major discrepancies flagged | DS-2.1–DS-2.4 | no LLM call |
| Resource limit enforcement | Configure 256 MB memory; execute memory-intensive notebook; assert OOM termination + finding | DS-3.1–DS-3.4 | no LLM call |
| Docker-unavailable fallback | Environment without Docker → assert graceful local-execution fallback with warning | DS-1.5 | no LLM call |

Source validation mapping: §7.8 scenarios map 1:1 to the rows above (resource-limit scenario uses 256 MB as the test override of the 4 GB default).

### Open Questions

- **OW-7 (FR-8.1):** The base image is "configurable" but the source names no default image or resolution rule (e.g., which image when no dependency file exists). Interpretation: default to a minimal Python image matching the notebook's kernel; confirm.
- **OW-8 (FR-8.2):** "Configurable tolerance" is named but no default numeric tolerance is given. Interpretation: pick a relative/absolute default (e.g., relative 1e-6) and make it configurable; confirm.
- **OW-9 (FR-8.2):** The PRD flags "output comparison" as deterministic and runnable in sandbox, but the desktop iteration has no sandbox (§6.5). Interpretation: in the desktop build, execution verification falls back to in-process execution (DS-1.5 semantics) and comparison still applies.

---

## 9. Non-Functional Requirements

Source: PRD §5. All numeric thresholds are reproduced **exactly** as in the source. Verification classification is per requirement type.

### NFR-1 — Performance (Local LLM Inference Latency)

| ID | Testable statement | Threshold (exact) | Priority | Verification | LLM involved |
|---|---|---|---|---|---|
| NFR-1.1 | A full six-pass audit on a notebook of ~500 lines completes within the bound, including LLM inference for subjective passes. | < 3 minutes | Must | Timed end-to-end run on a reference notebook | Mixed |
| NFR-1.2 | Each LLM-as-a-Judge invocation returns within the bound. Local: < 7B params, quantised. Cloud: OpenAI. | local ≤ 30 s; cloud ≤ 15 s | Must | Timed per-invocation; instrumented client | LLM-as-a-Judge |
| NFR-1.3 | All deterministic verification checks (dependency resolution, file existence, output comparison) complete within the bound, total. | < 5 s total | Must | Timed batch of deterministic checks | no LLM call |
| NFR-1.4 | A 2 MB `.ipynb` file parses and validates within the bound. | < 2 s | Should | Timed parse+validate of a synthetic 2 MB file | no LLM call |
| NFR-1.5 | JSON/MD export generates within the bound; PDF (full report) within its bound. | JSON/MD < 1 s; PDF < 10 s | Should | Timed export on a full report | no LLM call |

### NFR-2 — Offline Capability (Local-First)

| ID | Testable statement | Threshold (exact) | Priority | Verification | LLM involved |
|---|---|---|---|---|---|
| NFR-2.1 | The full audit pipeline (all six passes) runs using only local LLM inference (llama.cpp or Ollama) with zero internet connectivity. | zero internet connectivity required | Must | Full audit with network disabled | no LLM call for connectivity |
| NFR-2.2 | Users can download, list, and remove local GGUF models from HuggingFace without any cloud dependency for the core audit workflow. | no cloud dependency for core audit | Must | Model management with network disabled after download | no LLM call |
| NFR-2.3 | If a cloud provider is configured but unreachable, the system falls back to the configured local provider or notifies the user with a clear error. | fallback OR clear error | Should | Simulated cloud outage during audit | no LLM call |
| NFR-2.4 | All user configuration, audit history, and model selections are stored locally and survive application restarts. | survives restarts | Must | Restart test asserting state restoration | no LLM call |

### NFR-3 — Cross-Platform

| ID | Testable statement | Threshold (exact) | Priority | Verification | LLM involved |
|---|---|---|---|---|---|
| NFR-3.1 | The desktop application runs on the listed OS targets. | macOS 14+; Linux Ubuntu 22.04+, Fedora 38+; Windows 10+ / 11+ | Must | CI smoke build + launch on each target | no LLM call |
| NFR-3.2 | The system detects and utilises the available GPU backend on each platform. | Metal (macOS); CUDA (Linux/Windows); ROCm (Linux AMD) | Must | Hardware detection matrix test per OS | no LLM call |
| NFR-3.3 | Path handling, config locations, and model storage follow platform conventions. | `~/.test-prompts/` on Unix; equivalent on Windows | Must | Path-resolution unit tests per OS | no LLM call |
| NFR-3.4 | Docker sandbox is a Should requirement; on platforms without Docker the sandbox is skipped with a clear warning, not a hard error. | skip with warning, never hard error | Should | Sandbox invocation on a Docker-less host | no LLM call |

### NFR-4 — Security (Sandbox Isolation, Local Data Privacy)

| ID | Testable statement | Threshold (exact) | Priority | Verification | LLM involved |
|---|---|---|---|---|---|
| NFR-4.1 | All notebook content and audit data remain on the local machine unless the user explicitly configures a cloud provider. | no egress unless cloud configured | Must | Network egress monitor during local audit | no LLM call |
| NFR-4.2 | Notebook execution inside Docker has no access to the host filesystem except the explicitly mounted notebook and output directories. | host FS inaccessible except mounts | Must | Container isolation test attempting host reads | no LLM call |
| NFR-4.3 | Cloud provider API keys are stored in the OS keychain or encrypted config — never plaintext, never in notebook metadata. | keychain/encrypted only | Must | Key storage audit + search for plaintext keys | no LLM call |
| NFR-4.4 | Pass 6 scans for email addresses, API keys, and file paths that could leak sensitive information, by default. | on by default | Should | Fixture notebook with planted secrets | no LLM call (static scan) |
| NFR-4.5 | Docker sandbox containers run with `--network none` by default; network access requires explicit user opt-in. | `--network none` default | Should | Container inspect assert on network mode | no LLM call |

### NFR-5 — Extensibility (Provider-Agnostic Strategy Pattern)

| ID | Testable statement | Threshold (exact) | Priority | Verification | LLM involved |
|---|---|---|---|---|---|
| NFR-5.1 | New LLM providers are addable via a registered Python class implementing `LLMProvider` without modifying existing audit or orchestration code. | zero changes to audit/orchestration code | Must | Add a stub provider in a plugin dir; run pipeline unchanged | no LLM call |
| NFR-5.2 | Users can implement custom audit passes and register them in the pipeline alongside the six standard passes. | custom passes alongside standard | Could | Register a stub pass; assert it executes in order | no LLM call |
| NFR-5.3 | The Construction Workbench section template, LLM-as-a-Judge prompt templates, and report templates are user-overridable. | all three template kinds overridable | Should | Override each template kind; assert effect | no LLM call |
| NFR-5.4 | The full-stack version exposes a public REST API enabling third-party tools to trigger audits and retrieve results programmatically. | REST API for audit trigger + retrieval | Could | API integration test (full-stack only) | no LLM call |

### NFR-6 — Multi-OS GPU Support

| ID | Testable statement | Threshold (exact) | Priority | Verification | LLM involved |
|---|---|---|---|---|---|
| NFR-6.1 | The system accurately detects available GPU hardware: Metal on macOS, CUDA via `nvidia-smi` on Linux/Windows, ROCm via `rocm-smi` on Linux AMD. | detection per OS backend | Must | Detection matrix on each OS | no LLM call |
| NFR-6.2 | Users can configure `n_gpu_layers` for llama.cpp: -1 = all GPU layers, 0 = CPU only, N = N layers on GPU. | -1 / 0 / N semantics | Must | Config round-trip + layer-count assert | no LLM call |
| NFR-6.3 | When no GPU is detected, the system configures the LLM for CPU-only inference without error. | CPU-only fallback, no error | Must | Simulated no-GPU environment | no LLM call |
| NFR-6.4 | Based on detected hardware (RAM, GPU VRAM, OS), the system recommends appropriate model sizes and quantisations. | recommendation based on RAM/VRAM/OS | Should | Deterministic recommendation unit tests | no LLM call |

---

## Appendix: Ambiguities & Interpretations

The following source points were ambiguous or silent; each has a recorded interpretation and an open-question ID for owner confirmation. None of these add scope — they fix behavior where the source does not specify it.

| # | Source point | Ambiguity | Interpretation used in this spec |
|---|---|---|---|
| OW-1 | FR-1.3 / AC1.3.2 | No definition of the "previously captured snapshot" baseline for a first validation run. | First run captures the snapshot; subsequent runs compare. |
| OW-2 | FR-1.3 | "Output correctness" not quantified for non-numeric outputs. | Reuse FR-8.2 deterministic comparison primitives where applicable. |
| OW-3 | FR-2.8 / AC2.8.1 | Gate trigger defined only for High-risk reproducibility at Level 1. | Apply "gate on High risk within the completed level" at every level boundary; Moderate proceeds. |
| OW-4 | FR-3.3 / AC3.3.3 | Shape of the "fallback pass result" for malformed LLM output unspecified. | status `error`, zero findings, raw response in metadata, one synthetic `info` finding. |
| OW-5 | FR-3.1 / AC3.1.1 | `embed()` has no documented consumer in the PRD. | Implement as contract; no pipeline consumer this iteration. |
| OW-6 | FR-6.2 | No refresh-token strategy, JWT expiry default, or revocation semantics. | Configurable expiry + server-side revocation list (full-stack). |
| OW-7 | FR-8.1 / AC8.1.1 | No default sandbox base image or resolution rule. | Minimal Python image matching the notebook's kernel. |
| OW-8 | FR-8.2 / AC8.2.2 | "Configurable tolerance" without a default value. | Relative default (1e-6) + configurable. |
| OW-9 | FR-8.2 / §6.5 | Output comparison is sandbox-only, but the desktop build has no sandbox. | Desktop falls back to in-process execution (DS-1.5 semantics); comparison still applies. |

---

## Change Log

| Date | Version | Change |
|---|---|---|
| 2026-08-03 | v0.1 | Initial AI-ready spec derived from PRD-AgenticAI-Modular.md (v1.0). |
