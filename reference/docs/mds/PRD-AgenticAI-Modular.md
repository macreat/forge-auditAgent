# Product Requirements Document: Modular Agentic AI Environment

| **Document** | Product Requirements Document (PRD) |
|---|---|
| **System** | forge-auditAgent — Modular Agentic AI Environment |
| **Version** | 1.0 |
| **Status** | Draft |
| **Methodology** | Ian Sommerville — Iterative Requirements Engineering Spiral (Elicitation → Specification → Validation) |

---

## 1. Executive Summary

This document defines the product requirements for a **modular local generative AI agent environment** purpose-built for notebook construction and audit workflows. The system provides a unified platform where data scientists, ML engineers, and researchers can author Jupyter notebooks under a disciplined construction framework, systematically review them through a six-pass audit protocol, and orchestrate LLM-as-a-Judge evaluations across provider-agnostic backends — all running locally with optional cloud augmentation.

The system is designed as a **local-first, modular platform** with two operational tracks:

- **Notebook Construction Workbench** — guides authors through a three-phase disciplined authoring process (Scaffold → Write → Validate During Writing) with structural templates, reproducibility controls, and incremental validation gates.
- **Notebook Audit Engine** — executes a six-pass audit protocol (Structural Overview → Reproducibility → Data Integrity → ML Correctness → Code Quality → Deployment Readiness), organised into three conceptual levels with gate decisions between them: Conceptual (Passes 1–2), Methodological (Passes 3–4), and Implementation (Passes 5–6).

A current desktop implementation exists as a Flet application (`test/prompts/`) with hardware detection, local LLM inference via `llama-cpp-python`, HuggingFace GGUF model downloads, and the six-pass audit pipeline. The full-stack future architecture targets a Vite + React 18 frontend, FastAPI async backend, PostgreSQL audit session storage, Docker sandboxed notebook execution, and SSE-streamed real-time audit progress.

The requirements in this document are structured according to Sommerville's iterative spiral model, progressing through stakeholder elicitation, formal specification, and validation criteria for each requirement.

---

## 2. Scope & Context

### 2.1 Business Problem

Jupyter Notebooks are the de facto standard for exploratory data science, ML experimentation, and academic publication. However, they are notoriously difficult to review, reproduce, and productionise. Common pain points include: untracked dependency drift, hidden global state across cells, data leakage in ML pipelines, missing random seed pinning, hardcoded paths, bloated cell outputs, and absence of any structured quality gate before deployment or publication.

Teams currently lack a **unified tool** that:
- Guides the *author* through a disciplined construction process rather than leaving notebook structure to individual discipline.
- Provides a *reviewer* with a systematic, repeatable audit protocol — not ad hoc human inspection.
- Leverages **LLM-as-a-Judge** to scale subjective assessments (documentation quality, methodological soundness, code clarity) while maintaining deterministic verification for objective checks (dependency resolution, file existence, execution).
- Runs **locally by default** so that sensitive data never leaves the user's machine, with optional cloud augmentation for higher-capability models.

### 2.2 Business Opportunity

The system opens several strategic opportunities:

- **AI-assisted code review at scale**: replace unstructured peer review with a systematic six-pass protocol that catches issues human reviewers routinely miss.
- **Publication-grade reproducibility**: academic journals and conferences increasingly require reproducibility checks; this system automates that verification.
- **Enterprise ML governance**: provide audit trails for every notebook submitted to production, with signed reports and pass/fail gates.
- **Training & onboarding**: new team members follow the Construction Framework's guided workflow, internalising reproducible practices by tool enforcement rather than documentation.
- **Multi-provider LLM orchestration**: local models (Ollama, llama.cpp) protect privacy; cloud models (OpenAI) provide higher judgment capability — the user chooses per session.

### 2.3 System Boundaries

**In scope:**
- Notebook loading and parsing from local `.ipynb` files and GitHub raw URLs.
- Three-phase Construction Workbench (Scaffold → Write → Validate During Writing) with section templates, seed configuration, and incremental validation.
- Six-pass Audit Engine with LLM-as-a-Judge integration at three levels.
- Provider-agnostic LLM orchestration layer supporting Ollama, llama.cpp (local), and OpenAI (cloud).
- Deterministic verification engine for objective audit checks (dependency resolution, file existence, execution verification).
- Real-time audit progress streaming (SSE for web, progress callbacks for desktop).
- Export and reporting in JSON, Markdown, and PDF formats.
- Docker sandbox for notebook execution isolation.
- User session management with audit history persistence.
- Multi-OS GPU acceleration detection and utilisation (Metal, CUDA, ROCm).

**Out of scope (for this PRD iteration):**
- Notebook IDE or editor — the system reads existing notebooks for audit; construction is a guided workflow, not a notebook replacement for JupyterLab/VS Code.
- Real-time collaborative editing.
- Public notebook registry or sharing platform.
- Notebook-to-script transpilation or deployment pipeline beyond audit recommendations.
- Third-party CI/CD integration (GitHub Actions, GitLab CI) — deferred to later iteration.
- ML model training or experiment tracking (the system audits notebooks that *do* this; it does not replace MLflow/Weights & Biases).

### 2.4 Stakeholders

| Stakeholder | Role | Key Concern |
|---|---|---|
| **Data Scientists** | Primary authors — create notebooks for experimentation | Guided construction workflow, automated quality gates, minimal friction |
| **ML Engineers** | Productionise notebook logic | Reproducibility verification, dependency pinning, deployment readiness scoring |
| **Technical Reviewers** | Peer-review notebooks before merging | Systematic audit protocol, consistent scoring, actionable findings |
| **Academic Researchers** | Publish reproducible results alongside papers | Publication-grade audit reports, end-to-end re-executability checks |
| **Team Leads / Managers** | Oversee notebook quality across the team | Audit dashboards, trend analysis, pass/fail rates per team |
| **AI-Assisted Code Generation Users** | Use LLMs to help write notebook code | LLM-as-a-Judge feedback on code quality, documentation completeness |
| **ML Ops / Platform Engineers** | Maintain the agentic environment | Extensibility of providers, Docker sandbox configuration, plugin architecture |

---

## 3. Requirements Elicitation — Spiral Turn 1

### 3.1 Stakeholder Identification

Stakeholders were identified through an analysis of the notebook development lifecycle and the known operational roles required for a notebook review and authoring platform. The full stakeholder list is documented in §2.4.

### 3.2 User Needs and Goals

The following needs were elicited from stakeholder roles:

| Need ID | Stakeholder | Need Statement | Priority |
|---|---|---|---|
| N-01 | Data Scientists | "I need a guided workflow that helps me structure a new notebook with the right sections and reproducibility controls from the start." | High |
| N-02 | Technical Reviewers | "I need to run a systematic audit on any notebook in under a minute, not spend hours manually checking each cell." | High |
| N-03 | ML Engineers | "I need to know if a notebook's dependencies are pinned and if it can execute end-to-end on a fresh environment." | High |
| N-04 | Academic Researchers | "I need a formal audit report I can include in my paper's supplementary materials to prove reproducibility." | High |
| N-05 | All | "I need the system to work fully offline — my data must never be sent to the cloud unless I explicitly allow it." | Must |
| N-06 | Data Scientists | "I need the LLM to give me actionable recommendations on methodology and code quality, not just risk scores." | Should |
| N-07 | ML Ops Engineers | "I need to be able to add new LLM providers without modifying the core audit logic." | Should |
| N-08 | Team Leads | "I need to review audit history across notebooks and team members to track quality trends." | Could |
| N-09 | Technical Reviewers | "I need to scope an audit to specific focus areas (e.g., only data leakage and ML correctness) and skip irrelevant passes." | High |
| N-10 | Data Scientists | "I need the construction workbench to validate my notebook incrementally — check section by section as I write, not just at the end." | High |

### 3.3 Domain Terminology

The following terms were established during elicitation to ensure a shared vocabulary across stakeholders and development teams:

| Term | Definition |
|---|---|
| **Notebook** | A Jupyter `.ipynb` file containing code cells, markdown cells, and execution outputs in JSON format. |
| **Construction Framework** | A three-phase guided workflow (Scaffold → Write → Validate During Writing) for authoring well-structured, reproducible notebooks. |
| **Audit Framework** | A six-pass review protocol for systematically assessing notebook quality, correctness, and risk profile. |
| **Audit Pass** | A single review dimension within the Audit Framework (e.g., Structural Overview, Reproducibility). Each pass produces a risk score (Low / Moderate / High) and a list of findings. |
| **LLM-as-a-Judge** | The paradigm of using a large language model to evaluate subjective criteria such as documentation quality, methodological soundness, and code clarity. |
| **Provider-Agnostic Orchestration** | A strategy pattern that abstracts LLM inference behind a common interface, supporting Ollama, llama.cpp, and OpenAI interchangeably. |
| **Gate Decision** | A checkpoint between audit levels where the reviewer decides whether to proceed, stop, or escalate based on blocking issues found at the current level. |
| **Deterministic Verification** | Objective, rule-based checks (dependency resolution, file existence, execution verification) that do not require an LLM. |
| **Sandbox Execution** | Running a notebook inside an isolated Docker container to prevent host system contamination during audit execution checks. |
| **Section Header** | A canonical markdown heading within a notebook (Environment & Dependencies, Configuration, Data Ingestion, etc.) defined by the Construction Framework. |
| **Cell Idempotency** | The property that a code cell produces the same result when re-executed independently, regardless of execution order. |
| **GGUF** | A file format for quantised machine learning models, used by the llama.cpp ecosystem for local LLM inference. |
| **SSE (Server-Sent Events)** | A unidirectional streaming protocol used to push real-time audit progress from backend to frontend. |

---

## 4. Functional Requirements

Requirements are organised by system module. Each requirement follows the format:
**ID**, **Title**, **Description**, **Priority** (Must / Should / Could), **Acceptance Criteria**.

### 4.1 Notebook Construction Workbench

| Field | Value |
|---|---|
| **FR-1.1** | **Guided Scaffold Creation** |
| **Description** | The workbench MUST guide the user through creating a new notebook structure by presenting the canonical section headers (Environment & Dependencies, Configuration & Global Parameters, Data Ingestion, Preprocessing & Feature Engineering, Model Definition & Training, Evaluation & Metrics, Artifact Export, Conclusions & Next Steps) as an interactive template. |
| **Priority** | Must |
| **Acceptance Criteria** | AC1.1.1: The template generates a `.ipynb` file with all eight canonical section headers as markdown cells in the correct order. AC1.1.2: Each section includes a brief placeholder markdown description of its purpose. AC1.1.3: The user can customise, reorder, or remove sections before finalising. AC1.1.4: A requirements.txt or environment.yml placeholder cell is created in the Environment section. |

| Field | Value |
|---|---|
| **FR-1.2** | **Reproducibility Configuration Wizard** |
| **Description** | The workbench MUST prompt the user to configure global reproducibility controls: random seeds, deterministic flags, device configuration, and dependency file location. |
| **Priority** | Must |
| **Acceptance Criteria** | AC1.2.1: Wizard collects random seed values for numpy, torch, random, and sklearn. AC1.2.2: Generated notebook cells pin these values before any stochastic operation. AC1.2.3: Dependency file path (requirements.txt / conda.yaml / pyproject.toml) is recorded in notebook metadata. |

| Field | Value |
|---|---|
| **FR-1.3** | **Incremental Validation During Writing** |
| **Description** | After completing each section, the workbench MUST offer to restart the kernel and re-execute all cells up to that point, verifying cell idempotency and output correctness before allowing the author to proceed to the next section. |
| **Priority** | Should |
| **Acceptance Criteria** | AC1.3.1: The workbench detects when a new section header cell has been added and prompts validation. AC1.3.2: Validation includes kernel restart, full re-execution, and comparison of outputs to previously captured snapshots. AC1.3.3: Cell idempotency violations are flagged with cell index and expected vs actual output summary. AC1.3.4: The author can dismiss the prompt and continue without validation (override). |

| Field | Value |
|---|---|
| **FR-1.4** | **Output & Artifact Routing** |
| **Description** | The workbench MUST enforce a single, versioned export convention per section: all persisted outputs (models, plots, reports) must be routed through a defined output directory with versioned or timestamped filenames. |
| **Priority** | Should |
| **Acceptance Criteria** | AC1.4.1: The user defines an output root at scaffold time (default: `./output/`). AC1.4.2: Artifact export cells are checked to ensure writable paths fall under the output root. AC1.4.3: Ad-hoc writes outside the output root are flagged as findings. |

### 4.2 Notebook Audit Engine (Six Passes)

| Field | Value |
|---|---|
| **FR-2.1** | **Pass 1 — Structural Overview** |
| **Description** | The audit engine MUST map the notebook's section headers, verify linear execution order, identify immediately visible red flags (missing outputs, broken imports, orphaned cells), and record any user-specified focus areas that scope the remaining passes. |
| **Priority** | Must |
| **Acceptance Criteria** | AC2.1.1: Produces a section map listing all markdown headers with line numbers. AC2.1.2: Flags cells with out-of-order execution counts or hidden dependencies. AC2.1.3: Lists preliminary red flags with cell references. AC2.1.4: Deliverable includes the recorded focus-area scope. |

| Field | Value |
|---|---|
| **FR-2.2** | **Pass 2 — Reproducibility Check** |
| **Description** | The audit engine MUST verify dependency declarations are version-pinned, random seeds are set globally, flag hardcoded file paths or credentials, and assess end-to-end re-executability on a fresh kernel. |
| **Priority** | Must |
| **Acceptance Criteria** | AC2.2.1: Verifies presence of requirements.txt, conda.yaml, or pyproject.toml with pinned versions. AC2.2.2: Checks for global seed setting (numpy, torch, random, sklearn) before any stochastic operation. AC2.2.3: Flags absolute file paths, environment variables, API keys, or credentials. AC2.2.4: Deliverable: Reproducibility risk score (Low / Moderate / High). |

| Field | Value |
|---|---|
| **FR-2.3** | **Pass 3 — Data Integrity Review** |
| **Description** | The audit engine MUST examine the data pipeline for correctness: confirm train/test split ordering, identify data leakage (scalers or encoders fitted on full dataset), verify consistent missing-data handling across splits, and validate data types/shapes at ingestion. |
| **Priority** | Must |
| **Acceptance Criteria** | AC2.3.1: Identifies train/test split cell and confirms it precedes preprocessing. AC2.3.2: Flags any scaler, encoder, or imputer fitted on the full dataset. AC2.3.3: Checks that missing-data strategy is fit on training data only. AC2.3.4: Flags missing dtype or shape validation at ingestion. AC2.3.5: Deliverable: Data pipeline integrity report. |

| Field | Value |
|---|---|
| **FR-2.4** | **Pass 4 — ML Correctness Audit** |
| **Description** | The audit engine MUST evaluate ML methodology: confirm evaluation metric appropriateness for the task and class distribution, verify cross-validation integrity, check hyperparameter tuning boundaries (validation data only), and ensure baseline comparison is present. |
| **Priority** | Must |
| **Acceptance Criteria** | AC2.4.1: Flags inappropriate metrics (e.g., accuracy on imbalanced classification). AC2.4.2: Verifies CV folds preserve train/test separation. AC2.4.3: Confirms hyperparameter tuning uses validation data only. AC2.4.4: Flags missing baseline comparison. AC2.4.5: Deliverable: ML correctness checklist. |

| Field | Value |
|---|---|
| **FR-2.5** | **Pass 5 — Code Quality Review** |
| **Description** | The audit engine MUST assess code maintainability: flag repetitive blocks exceeding three-instance threshold, identify dead code and unused imports, evaluate naming quality, and check output hygiene (bloated dataframe printing, raw tensor dumps). |
| **Priority** | Must |
| **Acceptance Criteria** | AC2.5.1: Identifies code patterns repeated across three or more cells as refactoring candidates. AC2.5.2: Flags unused imports and dead code paths. AC2.5.3: Flags non-descriptive variable names (df1, tmp, x2). AC2.5.4: Flags large cell outputs without truncation. AC2.5.5: Deliverable: Code quality and smell report. |

| Field | Value |
|---|---|
| **FR-2.6** | **Pass 6 — Deployment Readiness** |
| **Description** | The audit engine MUST assess production or publication readiness: verify versioned artifact export, confirm inference/training separability, check resource documentation, ensure complete environment export, and flag PII/data privacy concerns. |
| **Priority** | Must |
| **Acceptance Criteria** | AC2.6.1: Verifies model/plot/report artifacts are saved with versioned or timestamped filenames. AC2.6.2: Checks that inference logic is separable from training. AC2.6.3: Flags missing compute/memory resource documentation. AC2.6.4: Confirms environment export is present and up to date. AC2.6.5: Flags any PII or credentials visible in notebook source. AC2.6.6: Deliverable: Deployment readiness score (Low / Moderate / High). |

| Field | Value |
|---|---|
| **FR-2.7** | **Scoped Audit Execution** |
| **Description** | The user MUST be able to specify focus areas or exclusions that limit which passes are executed. The structural pass (Pass 1) always runs to establish scope context. |
| **Priority** | Must |
| **Acceptance Criteria** | AC2.7.1: User provides a list of focus area labels (e.g., "data leakage", "code style"). AC2.7.2: Only passes matching the focus areas are executed (plus Pass 1). AC2.7.3: Skipped passes are marked with status "skipped" in the report. |

| Field | Value |
|---|---|
| **FR-2.8** | **Gate Decisions Between Levels** |
| **Description** | The audit engine MUST expose interactive gate decision points between Level 1 (Passes 1–2), Level 2 (Passes 3–4), and Level 3 (Passes 5–6), allowing the user to halt, continue, or escalate before proceeding. |
| **Priority** | Should |
| **Acceptance Criteria** | AC2.8.1: After Level 1 completion, if reproducibility is High Risk, a gate prompt is shown. AC2.8.2: User can choose "stop and flag", "continue to Level 2", or "escalate to human reviewer". AC2.8.3: The gate decision and rationale are recorded in the audit report. |

### 4.3 LLM Orchestration (Provider-Agnostic, Three-Level Audit)

| Field | Value |
|---|---|
| **FR-3.1** | **Provider Abstraction Layer** |
| **Description** | The LLM orchestration module MUST expose a common interface (`LLMProvider`) with methods for `chat_completion()`, `stream_chat()`, and `embed()` that all providers implement. |
| **Priority** | Must |
| **Acceptance Criteria** | AC3.1.1: `LLMProvider` is an abstract base class or Protocol with the required method signatures. AC3.1.2: At least three implementations exist: `OllamaProvider`, `LlamaCppProvider`, `OpenAIProvider`. AC3.1.3: New providers can be registered via a plugin registry without modifying existing provider code. AC3.1.4: Provider selection is configurable at runtime without service restart. |

| Field | Value |
|---|---|
| **FR-3.2** | **Deterministic Verification Engine** |
| **Description** | For objective audit checks (dependency resolution, file existence, environment presence, execution verification), the system MUST execute rule-based checks without invoking any LLM. |
| **Priority** | Must |
| **Acceptance Criteria** | AC3.2.1: Dependency checks parse requirements.txt/conda.yaml for version pins — no LLM call. AC3.2.2: File existence checks use OS filesystem APIs. AC3.2.3: Execution verification runs the notebook (or cells) in a sandbox and captures exit codes. AC3.2.4: Deterministic results are combined with LLM-judged results in the final report. |

| Field | Value |
|---|---|
| **FR-3.3** | **LLM-as-a-Judge for Subjective Passes** |
| **Description** | For subjective criteria (documentation quality, methodological coherence, code naming, output hygiene), the system MUST invoke the configured LLM provider with structured prompt templates and parse the response into structured findings. |
| **Priority** | Must |
| **Acceptance Criteria** | AC3.3.1: Each audit level (Conceptual, Methodological, Implementation) has a corresponding prompt template. AC3.3.2: LLM response is parsed into a list of `Finding` objects with severity, cell index, and message. AC3.3.3: Parsing errors or malformed LLM responses are handled gracefully with a fallback pass result. AC3.3.4: The exact prompt sent and raw LLM response are logged in the audit report metadata for transparency. |

| Field | Value |
|---|---|
| **FR-3.4** | **Three-Level Audit Execution** |
| **Description** | The audit engine MUST execute the six passes grouped into three levels: Level 1 — Conceptual (Passes 1–2), Level 2 — Methodological (Passes 3–4), Level 3 — Implementation (Passes 5–6), with gate decisions between levels. |
| **Priority** | Must |
| **Acceptance Criteria** | AC3.4.1: Level 1 always executes first. AC3.4.2: Level 2 begins only after Level 1 completes and optional gate is resolved. AC3.4.3: Level 3 begins only after Level 2 completes and optional gate is resolved. AC3.4.4: Each level produces its own deliverable subset of the final report. |

| Field | Value |
|---|---|
| **FR-3.5** | **Human-in-the-Loop Gate** |
| **Description** | The system MUST support an optional human review step at each gate decision, where findings from the completed level are presented to a human reviewer who must explicitly approve before the next level executes. |
| **Priority** | Could |
| **Acceptance Criteria** | AC3.5.1: Gate presents a summary of findings for the completed level. AC3.5.2: Human reviewer can approve, reject with reason, or request modifications. AC3.5.3: The reviewer's decision and any notes are recorded in the audit report. |

### 4.4 Notebook Loading & Parsing

| Field | Value |
|---|---|
| **FR-4.1** | **Local .ipynb File Loading** |
| **Description** | The system MUST load and parse local `.ipynb` files, extracting cells, metadata, execution counts, and outputs into the internal `Notebook` data model. |
| **Priority** | Must |
| **Acceptance Criteria** | AC4.1.1: Loads any valid `.ipynb` file (v4 or v4.x format). AC4.1.2: Extracts and categorises cells as `code` or `markdown`. AC4.1.3: Preserves execution counts, cell metadata, and output data. AC4.1.4: Invalid or corrupt `.ipynb` files produce a descriptive validation error. |

| Field | Value |
|---|---|
| **FR-4.2** | **GitHub URL Notebook Loading** |
| **Description** | The system MUST accept a GitHub raw URL pointing to a `.ipynb` file, fetch it via HTTP, and parse it identically to a local file. |
| **Priority** | Should |
| **Acceptance Criteria** | AC4.2.1: Accepts URLs matching `https://raw.githubusercontent.com/.../*.ipynb`. AC4.2.2: Downloads and caches the notebook temporarily (ephemeral, not persisted). AC4.2.3: Reports download errors (HTTP 404, timeout, invalid URL) with actionable messages. AC4.2.4: Parsed notebook is indistinguishable from a locally loaded notebook in downstream passes. |

| Field | Value |
|---|---|
| **FR-4.3** | **Notebook Validation on Load** |
| **Description** | On load, the system MUST validate the notebook structure: valid JSON schema, recognised cell types, linear execution count ordering, and non-empty cell arrays. |
| **Priority** | Must |
| **Acceptance Criteria** | AC4.3.1: JSON schema validation rejects malformed `.ipynb` files. AC4.3.2: Unknown or invalid cell types produce warnings but do not abort loading. AC4.3.3: Non-linear or reset execution counts are flagged as findings. AC4.3.4: Empty notebooks (zero cells) produce a validation error. |

### 4.5 Export & Reporting

| Field | Value |
|---|---|
| **FR-5.1** | **JSON Export** |
| **Description** | The system MUST export the full audit report as a structured JSON file containing all pass results, findings, scores, and metadata. |
| **Priority** | Must |
| **Acceptance Criteria** | AC5.1.1: JSON output includes all fields from the `AuditReport` and `PassResult` data models. AC5.1.2: Findings include severity, cell index, category, and message. AC5.1.3: The JSON schema is versioned and documented. AC5.1.4: Exported JSON can be re-imported for viewing or comparison. |

| Field | Value |
|---|---|
| **FR-5.2** | **Markdown Report Export** |
| **Description** | The system MUST generate a human-readable Markdown report summarising the audit results, suitable for inclusion in PR descriptions, documentation, or supplementary materials. |
| **Priority** | Must |
| **Acceptance Criteria** | AC5.2.1: Report includes notebook identity, overall status, and pass-by-pass findings. AC5.2.2: Risk scores are rendered with visual indicators (Low = ✅, Moderate = ⚠️, High = 🚫). AC5.2.3: Each finding is listed with cell reference and severity badge. AC5.2.4: Gate decisions (if recorded) are included as a timeline section. |

| Field | Value |
|---|---|
| **FR-5.3** | **PDF Report Export** |
| **Description** | The system MUST generate a printable PDF report with the same content as the Markdown report, formatted for academic submission or formal documentation. |
| **Priority** | Should |
| **Acceptance Criteria** | AC5.3.1: PDF includes title page with notebook name, timestamp, and overall score. AC5.3.2: Pass-level results are paginated with clear section headings. AC5.3.3: Risk scores are rendered as color-coded badges. AC5.3.4: PDF generation does not require external LaTeX installation (uses pure-Python PDF library). |

| Field | Value |
|---|---|
| **FR-5.4** | **Report Versioning & History** |
| **Description** | The system MUST maintain a chronological history of audit reports for each notebook, enabling comparison across audit runs. |
| **Priority** | Could |
| **Acceptance Criteria** | AC5.4.1: Each audit run is timestamped and stored with a unique run ID. AC5.4.2: User can view a list of past audit runs for a given notebook. AC5.4.3: User can compare two runs side-by-side, showing score deltas and new/resolved findings. |

### 4.6 User & Session Management

| Field | Value |
|---|---|
| **FR-6.1** | **Local Session Management** |
| **Description** | The desktop application MUST support persistent local sessions that remember the user's provider configuration, preferred model, audit history, and workspace paths across restarts. |
| **Priority** | Must |
| **Acceptance Criteria** | AC6.1.1: Configuration is persisted to `~/.test-prompts/config.json` (or equivalent platform path). AC6.1.2: Audit history is stored locally as JSON files in the audit directory. AC6.1.3: Session restores provider selection, model path, and last-opened notebook on launch. AC6.1.4: Configuration changes take effect immediately without restart. |

| Field | Value |
|---|---|
| **FR-6.2** | **Full-Stack User Authentication** |
| **Description** | The future full-stack version MUST support user registration and JWT-based authentication with role-based access control (admin, reviewer, author, viewer). |
| **Priority** | Should |
| **Acceptance Criteria** | AC6.2.1: Registration validates email uniqueness and password strength (min 8 chars, mixed case). AC6.2.2: Login returns a JWT access token with configurable expiry. AC6.2.3: Tokens are validated on every protected API endpoint. AC6.2.4: Author role can use the Construction Workbench. Reviewer role can run audits. Admin role manages users and system config. Viewer role has read-only access to reports. |

| Field | Value |
|---|---|
| **FR-6.3** | **Authentication-Free Local Mode** |
| **Description** | The desktop application MUST operate fully without authentication when running in local mode. Authentication is required only for multi-user features (shared audit history, team dashboards). |
| **Priority** | Must |
| **Acceptance Criteria** | AC6.3.1: Desktop app launches directly to the main workspace without login screen. AC6.3.2: All local features (loading notebooks, running audits, exporting reports) are available without authentication. AC6.3.3: Cloud features (shared history, remote provider calls via proxy) prompt for authentication on first use. |

### 4.7 Real-Time Progress & Visualization

| Field | Value |
|---|---|
| **FR-7.1** | **Audit Progress Streaming** |
| **Description** | The system MUST communicate audit progress in real time: which pass is currently executing, completion percentage, and partial findings as they are produced. |
| **Priority** | Must |
| **Acceptance Criteria** | AC7.1.1: Desktop app shows a progress bar per pass with status text. AC7.1.2: Each pass completion triggers a UI update with score and finding count. AC7.1.3: Errors during a pass are displayed immediately without halting the pipeline. AC7.1.4: Full-stack version uses SSE to stream progress events to the frontend. |

| Field | Value |
|---|---|
| **FR-7.2** | **Pass-by-Pass Results Display** |
| **Description** | After each pass completes, the system MUST display its findings in an expandable card or panel with the risk score, findings list, and deliverable text. |
| **Priority** | Should |
| **Acceptance Criteria** | AC7.2.1: Each pass result is shown as a distinct card with pass name, number, and score badge. AC7.2.2: Findings are listed with severity icon, cell reference, and message. AC7.2.3: Users can expand/collapse individual pass details. AC7.2.4: The full deliverable text is available via an expansion toggle. |

| Field | Value |
|---|---|
| **FR-7.3** | **Side-by-Side Comparison View** |
| **Description** | The system MUST support displaying two audit reports side-by-side for comparison, either from different runs on the same notebook or from different notebooks. |
| **Priority** | Could |
| **Acceptance Criteria** | AC7.3.1: Comparison view shows pass scores aligned on the same row. AC7.3.2: Findings that are new, resolved, or unchanged are visually distinguished. AC7.3.3: Score deltas are computed and displayed per pass. |

### 4.8 Docker Sandbox Execution

| Field | Value |
|---|---|
| **FR-8.1** | **Sandbox Notebook Execution** |
| **Description** | The system MUST execute the notebook (or selected cells) inside an isolated Docker container to verify reproducibility without contaminating the host environment. |
| **Priority** | Should |
| **Acceptance Criteria** | AC8.1.1: Sandbox container is created from a configurable base image with the notebook's declared dependencies installed. AC8.1.2: Notebook is copied into the container and executed via `jupyter nbconvert --execute`. AC8.1.3: Execution output is captured and compared to the original notebook's outputs. AC8.1.4: Container is destroyed after execution (ephemeral). AC8.1.5: Docker not available errors are handled gracefully (fallback to local execution with warning). |

| Field | Value |
|---|---|
| **FR-8.2** | **Output Comparison** |
| **Description** | The sandbox MUST compare execution output to the original notebook's stored outputs and flag discrepancies. |
| **Priority** | Should |
| **Acceptance Criteria** | AC8.2.1: Outputs are compared at the cell level (text output, error messages, rich display data). AC8.2.2: Numerical differences within a configurable tolerance are not flagged. AC8.2.3: Missing outputs (cells that produced no output in re-execution but had output originally) are flagged. AC8.2.4: New error outputs in re-execution are flagged as High severity. |

| Field | Value |
|---|---|
| **FR-8.3** | **Sandbox Resource Limits** |
| **Description** | The sandbox execution MUST enforce configurable resource limits (memory, CPU, disk, timeout) to prevent runaway notebook execution. |
| **Priority** | Should |
| **Acceptance Criteria** | AC8.3.1: Memory limit (default 4 GB) is enforced via Docker `--memory`. AC8.3.2: CPU limit (default 2 cores) is enforced via Docker `--cpus`. AC8.3.3: Execution timeout (default 30 minutes) is enforced; exceeded timeout terminates the container. AC8.3.4: Resource limits are configurable in the sandbox settings. |

---

## 5. Non-Functional Requirements

### NFR-1: Performance (Local LLM Inference Latency)

| ID | Requirement | Target | Priority |
|---|---|---|---|
| NFR-1.1 | **Audit Pipeline Completion** | A full six-pass audit on a notebook of ~500 lines must complete in under 3 minutes (including LLM inference for subjective passes). | Must |
| NFR-1.2 | **LLM Inference Latency** | Each LLM-as-a-Judge invocation must return within 30 seconds for local models (< 7B params, quantised) and within 15 seconds for cloud models (OpenAI). | Must |
| NFR-1.3 | **Deterministic Check Latency** | All deterministic verification checks (dependency resolution, file existence, output comparison) must complete in under 5 seconds total. | Must |
| NFR-1.4 | **Notebook Loading** | A 2 MB `.ipynb` file must parse and validate in under 2 seconds. | Should |
| NFR-1.5 | **Export Generation** | JSON/MD export must generate in under 1 second. PDF export (full report) must generate in under 10 seconds. | Should |

### NFR-2: Offline Capability (Local-First)

| ID | Requirement | Target | Priority |
|---|---|---|---|
| NFR-2.1 | **Fully Offline Audit** | The system must execute the full audit pipeline (all six passes) using only local LLM inference (llama.cpp or Ollama) with zero internet connectivity required. | Must |
| NFR-2.2 | **Local Model Management** | Users must be able to download, list, and remove local GGUF models from HuggingFace without any cloud dependency for the core audit workflow. | Must |
| NFR-2.3 | **Graceful Cloud Degradation** | If a cloud provider is configured but unreachable, the system must fall back to the configured local provider or notify the user with a clear error. | Should |
| NFR-2.4 | **Configuration Persistence** | All user configuration, audit history, and model selections must be stored locally and survive application restarts. | Must |

### NFR-3: Cross-Platform

| ID | Requirement | Target | Priority |
|---|---|---|---|
| NFR-3.1 | **Desktop OS Support** | The desktop application must run on macOS (14+), Linux (Ubuntu 22.04+, Fedora 38+), and Windows (10+ / 11+). | Must |
| NFR-3.2 | **GPU Backend Parity** | The system must detect and utilise the available GPU backend on each platform: Metal (macOS), CUDA (Linux/Windows), ROCm (Linux AMD). | Must |
| NFR-3.3 | **File System Consistency** | Path handling, configuration file locations, and model storage directories must follow platform conventions (`~/.test-prompts/` on Unix, equivalent on Windows). | Must |
| NFR-3.4 | **Docker Support Variance** | Docker sandbox is a Should requirement; on platforms without Docker Desktop (e.g., some Linux distributions without Docker installed), the sandbox is skipped with a clear warning rather than a hard error. | Should |

### NFR-4: Security (Sandbox Isolation, Local Data Privacy)

| ID | Requirement | Target | Priority |
|---|---|---|---|
| NFR-4.1 | **Data Sovereignty** | All notebook content and audit data must remain on the local machine unless the user explicitly configures a cloud provider. | Must |
| NFR-4.2 | **Sandbox Isolation** | Notebook execution inside Docker must have no access to the host filesystem except the explicitly mounted notebook and output directories. | Must |
| NFR-4.3 | **Credentials Protection** | API keys for cloud providers (OpenAI) must be stored in the OS keychain or encrypted config, never in plaintext or notebook metadata. | Must |
| NFR-4.4 | **PII Detection Default** | Pass 6 (Deployment Readiness) must scan for email addresses, API keys, and file paths that could leak sensitive information, by default. | Should |
| NFR-4.5 | **Network Isolation** | Docker sandbox containers must run with `--network none` by default; network access requires explicit user opt-in. | Should |

### NFR-5: Extensibility (Provider-Agnostic Strategy Pattern)

| ID | Requirement | Target | Priority |
|---|---|---|---|
| NFR-5.1 | **Provider Plugin Architecture** | New LLM providers must be addable via a registered Python class implementing `LLMProvider` without modifying existing audit or orchestration code. | Must |
| NFR-5.2 | **Custom Pass Support** | Users must be able to implement custom audit passes and register them in the pipeline alongside the six standard passes. | Could |
| NFR-5.3 | **Template Customisation** | The Construction Workbench's section template, prompt templates for LLM-as-a-Judge, and report templates must be user-overridable. | Should |
| NFR-5.4 | **API Surface** | The full-stack version must expose a public REST API enabling third-party tools to trigger audits and retrieve results programmatically. | Could |

### NFR-6: Multi-OS GPU Support

| ID | Requirement | Target | Priority |
|---|---|---|---|
| NFR-6.1 | **GPU Detection** | The system must accurately detect available GPU hardware: Metal on macOS, CUDA via `nvidia-smi` on Linux/Windows, ROCm via `rocm-smi` on Linux AMD. | Must |
| NFR-6.2 | **GPU Layer Configuration** | Users must be able to configure `n_gpu_layers` for llama.cpp (-1 = all GPU layers, 0 = CPU only, N = N layers on GPU). | Must |
| NFR-6.3 | **Graceful CPU Fallback** | When no GPU is detected, the system must configure the LLM for CPU-only inference without error. | Must |
| NFR-6.4 | **Hardware Recommendation** | Based on detected hardware (RAM, GPU VRAM, OS), the system should recommend appropriate model sizes and quantisations. | Should |

---

## 6. System Constraints

### 6.1 Technology Architecture

| Layer | Current (Desktop) | Planned (Full-Stack) |
|---|---|---|
| **Frontend** | Flet (Python GUI) | Vite + React 18 + TypeScript |
| **Backend API** | In-process | FastAPI (async) |
| **Database** | JSON file config + file-based audit history | PostgreSQL (audit sessions, config) |
| **LLM Integration** | llama-cpp-python (in-process server) | Provider-agnostic strategy pattern (Ollama, llama.cpp, OpenAI) |
| **Sandbox** | None (local execution only) | Docker per-notebook sandbox |
| **Real-Time Updates** | In-process callbacks | SSE streaming |
| **Deployment** | PyInstaller binary | Docker Compose (full-stack) |
| **GPU Support** | Metal, CUDA, ROCm | Same + expanded detection |

### 6.2 LLM Model Constraints

- **Local inference**: constrained by available RAM and GPU VRAM. Recommended models: 1–7B param quantised GGUF models fit on consumer hardware (8–32 GB RAM). Larger models (13B+) require cloud provider fallback or high-end workstation.
- **Context window**: constrained by model context size (typically 2048–8192 tokens for local models; 128K+ for cloud models). Audit prompt templates must fit within the model's context window.
- **Quantisation**: only GGUF format is supported for local llama.cpp inference. Other formats (AWQ, GPTQ, GGML) are out of scope.

### 6.3 Notebook Ecosystem Constraints

- The system targets **Jupyter `.ipynb` format (v4.x)** only. Other notebook formats (R Markdown, Quarto, Google Colab `.ipynb` without output, Zeppelin) are out of scope.
- Notebooks must be **JSON-parseable** and follow the Jupyter notebook schema. Heavily corrupted notebooks may not load.
- Tested with **Python kernels** (3.10+). R, Julia, or other kernels may parse but audit passes targeting Python-specific patterns (pip, numpy, sklearn, torch) will have reduced coverage.

### 6.4 Local-First Architecture

- All core functionality (notebook loading, audit pipeline, report export) must work with **zero internet connectivity**.
- Cloud providers (OpenAI) are **optional extensions** — never required for basic operation.
- The system must never send notebook content to a remote server unless the user explicitly configures and selects a cloud LLM provider for judgment passes.

### 6.5 Flet Desktop vs Future Full-Stack

| Constraint | Flet Desktop | Full-Stack (Future) |
|---|---|---|
| **Audit through-put** | Single-user, single pipeline | Multi-user, concurrent audits |
| **Real-time UI** | In-process callback → Flet UI update | SSE → React state → WebSocket push |
| **Multi-tenancy** | Not applicable | User accounts, RBAC, shared history |
| **Deployment** | Standalone binary | Docker Compose or Kubernetes |
| **Sandbox** | Not available — notebooks run in-process | Docker container isolation |
| **Audit History** | Local file-based | PostgreSQL with indexed queries |

---

## 7. Validation & Acceptance Criteria

This section defines how each requirement category is validated, following Sommerville's validation turn of the spiral.

### 7.1 Construction Workbench Validation

| Scenario | Validation Method | Requirement(s) |
|---|---|---|
| **Scaffold creation** | Launch scaffold wizard, select all eight canonical sections, verify generated `.ipynb` contains expected markdown cells and structure. | FR-1.1 |
| **Reproducibility config** | Create a notebook with the wizard, verify generated cells contain seed pinning and dependency declaration. | FR-1.2 |
| **Incremental validation** | Complete first section, trigger validation, verify kernel restarts and cells re-execute correctly. | FR-1.3 |
| **Artifact routing enforcement** | Write a cell that attempts to save output outside the designated output root. Verify it is flagged. | FR-1.4 |

### 7.2 Audit Engine Validation

| Scenario | Validation Method | Requirement(s) |
|---|---|---|
| **Full six-pass audit** | Submit a known notebook with deliberate issues (missing seeds, data leakage, repetitive code, hardcoded paths). Verify all six passes produce appropriate findings. | FR-2.1–FR-2.6 |
| **Scoped audit** | Run with focus areas `["data leakage", "code quality"]`. Verify only Pass 1, Pass 3, and Pass 5 execute; others are marked "skipped". | FR-2.7 |
| **Gate decision interaction** | Run Level 1 on a notebook that fails reproducibility. Verify gate prompt appears. Choose "continue" and verify Level 2 runs. | FR-2.8 |

### 7.3 LLM Orchestration Validation

| Scenario | Validation Method | Requirement(s) |
|---|---|---|
| **Provider abstraction** | Configure Ollama provider, run LLM-judged passes. Switch to llama.cpp provider, run same notebook. Verify both produce structurally identical results. | FR-3.1 |
| **Deterministic vs LLM separation** | Audit a notebook with pinned dependencies (deterministic check) and poor documentation (LLM check). Verify deterministic findings appear without any LLM call. | FR-3.2 |
| **Structured prompt parsing** | Send a known notebook to the Level 1 prompt. Verify the LLM response is parsed into valid `Finding` objects with correct severity and cell references. | FR-3.3 |
| **Three-level execution order** | Run full audit. Verify Level 1 completes before Level 2, Level 2 before Level 3. Verify gate resolution between each level. | FR-3.4 |

### 7.4 Notebook Loading Validation

| Scenario | Validation Method | Requirement(s) |
|---|---|---|
| **Local .ipynb load** | Load a valid `.ipynb` file with mixed code and markdown cells. Verify all cells are parsed correctly with execution counts preserved. | FR-4.1 |
| **GitHub URL load** | Load a notebook from a GitHub raw URL. Verify identical parsing to local load. | FR-4.2 |
| **Corrupt file handling** | Submit a malformed JSON file as `.ipynb`. Verify descriptive error message and graceful failure. | FR-4.3 |

### 7.5 Export Validation

| Scenario | Validation Method | Requirement(s) |
|---|---|---|
| **JSON export** | Run full audit, export JSON. Re-import JSON. Verify all fields match the in-memory report. | FR-5.1 |
| **Markdown export** | Run audit, export MD. Verify human-readable output with scores, findings, and cell references. | FR-5.2 |
| **PDF export** | Run audit, export PDF. Verify print-ready formatting with title page and paginated passes. | FR-5.3 |

### 7.6 Session & Auth Validation

| Scenario | Validation Method | Requirement(s) |
|---|---|---|
| **Local session persistence** | Configure provider and model, restart app. Verify settings are restored. | FR-6.1 |
| **Full-stack registration & login** | (Full-stack only) Register user, login, verify JWT returned. Attempt protected endpoint without token — verify HTTP 401. | FR-6.2 |
| **Local mode no auth** | Launch desktop app. Verify no login prompt appears. Verify all local features accessible. | FR-6.3 |

### 7.7 Real-Time Progress Validation

| Scenario | Validation Method | Requirement(s) |
|---|---|---|
| **Progress updates** | Run full audit on desktop. Verify progress bar advances through each pass with status text. | FR-7.1 |
| **SSE streaming** | (Full-stack only) Open audit page in browser, trigger audit. Verify SSE events arrive per pass with finding counts. | FR-7.1 |

### 7.8 Docker Sandbox Validation

| Scenario | Validation Method | Requirement(s) |
|---|---|---|
| **Sandbox execution** | Execute a notebook with pinned dependencies in Docker sandbox. Verify container is created, notebook runs, outputs captured, container destroyed. | FR-8.1 |
| **Output comparison** | Run a notebook where re-execution produces slightly different numerical output. Verify within-tolerance differences are not flagged but major discrepancies are. | FR-8.2 |
| **Resource limit enforcement** | Configure 256 MB memory limit, execute a memory-intensive notebook. Verify container is terminated with an OOM error and the finding is reported. | FR-8.3 |

### 7.9 Acceptance Test: End-to-End Scenario

A full end-to-end acceptance test shall be executed before the system is accepted. The test covers the entire happy path:

1. Launch the desktop application (Flet GUI or full-stack web).
2. Use the Construction Workbench to scaffold a new notebook with all eight sections and reproducibility configuration.
3. Write three sections of the notebook (Environment, Data Ingestion, Model Definition) with deliberate issues: unpinned dependency, missing seed, hardcoded path.
4. Trigger incremental validation after one section — verify kernel restart and clean execution.
5. Load the notebook into the Audit Engine.
6. Run a full six-pass audit with the local LLM provider.
7. Verify:
   - Pass 1 produces a section map and flags the hardcoded path.
   - Pass 2 flags the missing seed and unpinned dependency.
   - Pass 3 verifies data pipeline integrity (or notes no data pipeline present).
   - Pass 4 verifies ML methodology (or notes no ML section present for scoring).
   - Pass 5 flags any repetitive or poorly-named code.
   - Pass 6 produces a deployment readiness score.
8. At the Level 1 gate, observe the prompt and choose "continue".
9. Export the audit report in JSON, MD, and PDF formats. Verify each is well-formed and contains all pass results.
10. Re-import the JSON export. Verify the re-imported report matches the original.

This test constitutes the formal acceptance milestone for the system.

---

## 8. Glossary

| Term | Definition |
|---|---|
| **Audit Pipeline** | The sequential orchestrator that executes selected audit passes, collects results, and produces the final `AuditReport`. |
| **Cell Idempotency** | The property that a code cell produces the same output when re-executed independently, regardless of execution order or kernel state. |
| **Construction Framework** | A three-phase workflow (Scaffold → Write → Validate During Writing) for authoring well-structured, reproducible notebooks. |
| **Dependency Pinning** | The practice of specifying exact versions for all dependencies (e.g., `numpy==1.26.0`) rather than version ranges, ensuring reproducible environments. |
| **Deterministic Verification** | Objective, rule-based checks that do not require an LLM — dependency resolution, file existence, environment detection, output comparison. |
| **Finding** | A single issue identified by an audit pass, with severity (info/warning/error), cell index, category, and descriptive message. |
| **Gate Decision** | A checkpoint between audit levels where the user or human reviewer decides whether to proceed based on findings at the current level. |
| **GGUF** | A file format for quantised machine learning models, adopted by the llama.cpp ecosystem for local LLM inference. |
| **LLM Provider** | An abstraction implementing the `LLMProvider` interface (Ollama, LlamaCpp, OpenAI) that provides chat completion and embedding capabilities. |
| **LLM-as-a-Judge** | The paradigm of using an LLM to evaluate subjective criteria (documentation quality, methodology, code clarity) during an audit. |
| **Notebook** | A Jupyter `.ipynb` file containing code cells, markdown cells, metadata, and execution outputs in version 4.x JSON format. |
| **PassResult** | The output of a single audit pass: score (Low/Moderate/High), status (passed/flagged/skipped/error), findings list, and narrative deliverable text. |
| **Provider-Agnostic Strategy Pattern** | A design pattern where different LLM backends implement a common interface, allowing the same audit logic to use any provider without modification. |
| **Red Flag** | A critical issue identified during Pass 1 (Structural Overview) that is visible without deep inspection — missing outputs, broken imports, orphaned cells. |
| **Sandbox** | An isolated Docker container used to execute notebooks during the audit, preventing host system contamination. |
| **Scaffold** | The first phase of the Construction Framework — creating section headers, pinning dependencies, and configuring reproducibility controls before writing any logic. |
| **Section Header** | One of eight canonical markdown headings defined by the Construction Framework: Environment, Configuration, Data Ingestion, Preprocessing, Model Definition, Evaluation, Artifact Export, Conclusions. |
| **SSE (Server-Sent Events)** | A unidirectional HTTP streaming protocol used to push real-time audit progress events from the backend to the frontend. |
| **Three-Level Audit Model** | The grouping of the six audit passes into three levels: Conceptual (Passes 1–2), Methodological (Passes 3–4), Implementation (Passes 5–6), with gate decisions between levels. |

---

*End of Document — PRD Modular Agentic AI Environment v1.0*
