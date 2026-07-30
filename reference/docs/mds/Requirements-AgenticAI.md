# Requirements Document: Modular Agentic AI Environment

| **Document** | System Requirements Specification (SRS) |
|---|---|
| **System** | forge-auditAgent |
| **Version** | 1.0 |
| **Status** | Draft |

---

## 1. Problem Statement

Computational notebooks (Jupyter `.ipynb`) dominate data science and ML workflows, yet they introduce systemic risks at every stage of the lifecycle. Untrusted notebook execution, ad hoc environment pinning, missing dependency declarations, absent seed controls, and hidden global state across cells cause notebooks to produce different results across machines or sessions, undermining scientific validity. There is no structured, repeatable audit protocol for reviewing notebooks before production deployment, publication, or merge. Existing code review practices are insufficient for the unique failure modes of notebook-based ML pipelines: data leakage through preprocessing ordering, cross-validation contamination, and inseparable training/inference logic.

An environment is needed that enables teams to author notebooks under a disciplined construction framework, audit them through a systematic multi-pass protocol powered by LLM-as-a-Judge evaluation, and orchestrate AI agents locally with optional cloud augmentation — all while keeping sensitive data on the user's machine.

---

## 2. General System Description

The forge-auditAgent is a modular, local-first generative AI agent environment purpose-built for notebook lifecycle management. It operates on two integrated tracks:

- **Notebook Construction Workbench**: Guides authors through a three-phase disciplined authoring process (Scaffold → Write → Validate During Writing) with structural templates, reproducibility controls, and incremental validation gates.
- **Notebook Audit Engine**: Executes a six-pass audit protocol (Structural Overview, Reproducibility, Data Integrity, ML Correctness, Code Quality, Deployment Readiness) organised into three conceptual levels — Conceptual (Passes 1–2), Methodological (Passes 3–4), and Implementation (Passes 5–6) — with gate decisions between each level.

The system is implemented as a Flet desktop application (`test/prompts/`) with hardware detection, local LLM inference via `llama-cpp-python`, HuggingFace GGUF model downloads, and the full six-pass audit pipeline. A future full-stack architecture targets Vite + React 18, FastAPI, PostgreSQL, and Docker sandbox execution.

The Agentic AI workflow is implemented through eight integrated building blocks: Goal Definition, Task Decomposition, Planning, Tool Integration, Memory and Context Management, Decision-Making, Task Execution, and Human-in-the-Loop.

---

## 3. System Architecture

### 3.1 Hardware Architecture (Current Desktop)

```
[User Machine]
    |
    +-- CPU (x86_64 / ARM64)
    +-- RAM (≥ 8 GB recommended)
    +-- GPU (optional: Metal / CUDA / ROCm)
    |
    +-- [test/prompts/ Flet App]
    |       |
    |       +-- Hardware Detection Module
    |       +-- Model Download (HuggingFace Hub)
    |       +-- Local LLM Server (llama-cpp-python)
    |       +-- Audit Pipeline (6 passes)
    |       +-- Export Engine (JSON / MD / PDF)
    |
    +-- [Storage]
            +-- models/ (GGUF files)
            +-- notebooks/ (.ipynb files)
            +-- reports/ (audit exports)
```

### 3.2 Software Architecture

```
[Flet GUI - 6 Tabs]
    |
    +-- Hardware Tab
    +-- Models Tab
    +-- Server Tab
    +-- Settings Tab
    +-- Benchmark Tab
    +-- Audit Tab
            |
            +-- Notebook Loader (local / GitHub)
            +-- Focus Area Selector (6 checkboxes)
            +-- AuditPipeline.run()
            |       |
            |       +-- Pass 1: Structural Overview
            |       +-- Pass 2: Reproducibility Check
            |       +-- Pass 3: Data Integrity Review
            |       +-- Pass 4: ML Correctness Audit
            |       +-- Pass 5: Code Quality Review
            |       +-- Pass 6: Deployment Readiness
            |
            +-- Export Engine (JSON / PDF)

[LLM Orchestration]
    |
    +-- Local: llama-cpp-python (in-process server)
    +-- Local: Ollama API
    +-- Cloud: OpenAI API
    +-- Strategy Pattern: LLMProvider interface

[Memory / Persistence]
    |
    +-- Engram (persistent memory for decisions)
    +-- JSON config (~/.test-prompts/config.json)
    +-- Reports directory (audit outputs)
```

---

## 4. System Requirements

### 4.1 Functional Requirements (RF)

| ID | Description | Acceptance Criteria |
|---|---|---|
| RF-01 | The system SHALL load and parse `.ipynb` files from the local filesystem and validate JSON structure, cell types, and metadata integrity. | Valid notebooks return a `Notebook` object with `valid=True`. Malformed files return `valid=False` with descriptive errors. |
| RF-02 | The system SHALL fetch and parse notebooks from public GitHub raw URLs, auto-converting `github.com/blob/` URLs to `raw.githubusercontent.com/`. | URL normalisation succeeds; parsed notebook matches expected structure or returns clear error. |
| RF-03 | The system SHALL scan a local notebooks directory and present available files (`.ipynb`, `.py`, `.md`, `.txt`) in a dropdown for selection. | Directory scan finds all matching files; auto-loads the first valid notebook. |
| RF-04 | The Construction Workbench SHALL guide notebook authoring through three phases: Scaffold (section templates, dependency pinning, seed config), Write (incremental section authoring), and Validate (kernel restart, cell idempotency). | Each phase is visually distinct with clear prompts; section headers follow the canonical 8-section order. |
| RF-05 | The Audit Engine SHALL execute six sequential passes, each producing a structured deliverable with a risk score (Low/Moderate/High) or qualitative report. | All six passes run; each returns a `PassResult` with `pass_number`, `pass_name`, `status`, `score`, `findings`, and `deliverable_text`. |
| RF-06 | Pass 1 (Structural Overview) SHALL produce a section map, preliminary red flag list, and recorded focus-area scope. | Section headers identified; red flags for missing outputs, broken imports, orphaned cells reported. |
| RF-07 | Pass 2 (Reproducibility Check) SHALL verify dependency pinning, seed configuration, hardcoded paths, and end-to-end re-executability. | Risk score computed; dependency file presence and seed calls verified; hardcoded paths flagged. |
| RF-08 | Pass 3 (Data Integrity) SHALL verify train/test split ordering, data leakage signs, missing-data handling, and ingestion-time validation. | Pipeline integrity report generated; split-before-preprocessing rule enforced; leakage patterns flagged. |
| RF-09 | Pass 4 (ML Correctness) SHALL confirm evaluation metric appropriateness, cross-validation integrity, hyperparameter tuning boundaries, and baseline comparison. | Correctness checklist produced; metric-task alignment verified; CV leakage detected; baseline required. |
| RF-10 | Pass 5 (Code Quality) SHALL flag repetitive code blocks (≥3 threshold), dead code, naming quality, and output hygiene. | Code smell report generated; repetition threshold enforced; dead code and bloated outputs flagged. |
| RF-11 | Pass 6 (Deployment Readiness) SHALL verify artifact export, inference/training separability, resource documentation, environment completeness, and data privacy. | Risk score computed; artifact versioning, separation of concerns, and environment export verified. |
| RF-12 | The system SHALL evaluate notebooks using a hybrid strategy: deterministic checks for objective criteria and LLM judging for subjective criteria. | Deterministic checks run without API calls; LLM judging routes through configured provider. |
| RF-13 | The LLM orchestration layer SHALL support at least three providers: llama.cpp (in-process), Ollama (local API), and OpenAI (cloud API), interchangeable via a strategy pattern. | Each provider returns valid evaluations for identical prompts; provider switching does not require restart. |
| RF-14 | The system SHALL provide real-time audit progress via a progress callback or SSE stream, emitting one event per completed pass. | Progress callback fires after each pass with current result; UI updates within 500ms. |
| RF-15 | The system SHALL export audit reports in at least three formats: JSON, Markdown, and PDF. | Each export function produces a valid file at the specified path with complete report content. |
| RF-16 | The system SHALL provide a notebook database scanner that lists and loads files from `test/prompts/notebooks/`. | Scanner populates dropdown on click; first valid file loads automatically. |
| RF-17 | The system SHALL accept manual local file paths and load valid notebooks from them. | Path entry followed by "Load Local" loads the notebook or returns a clear error. |
| RF-18 | The system SHALL work fully offline for local-only operations (file loading, local LLM inference, audit pipeline execution). | All core functions operate without internet; cloud LLM usage is explicitly opt-in. |

### 4.2 Non-Functional Requirements (RNF)

| ID | Description | Acceptance Criteria |
|---|---|---|
| RNF-01 | The system SHALL run on Linux (WSL and native), macOS, and Windows, with GPU acceleration where available (Metal, CUDA, ROCm). | Application launches and core features work on all three platforms. |
| RNF-02 | The system SHALL start and become interactive within 5 seconds on a machine with ≥ 8 GB RAM and an SSD. | Measured from `python main.py` to responsive UI. |
| RNF-03 | Local LLM inference SHALL respond to audit prompts within 30 seconds for models ≤ 7B parameters on a CUDA-capable GPU. | Mean response time over 10 audit runs ≤ 30 s. |
| RNF-04 | The system SHALL gracefully handle missing optional dependencies (GPU libraries, cloud SDKs) without crashing on startup. | Application starts and shows relevant features as disabled or unavailable; no traceback on console. |
| RNF-05 | The audit pipeline SHALL complete all six passes for a notebook with ≤ 50 cells within 120 seconds (using deterministic checks + a local 7B model). | End-to-end audit time measured from Run Audit click to final result display. |
| RNF-06 | All user data (notebooks, models, config, reports) SHALL remain on the local machine by default; no data SHALL be sent to external services without explicit user action. | No outbound network requests during local-only operations; cloud LLM calls require user-initiated action. |
| RNF-07 | The system SHALL support concurrent operation with other GUI applications without noticeable degradation. | No frame drops or UI freezes beyond 200ms during audit pipeline execution. |
| RNF-08 | The LLM provider strategy SHALL be extensible to new providers without modifying existing provider implementations (Open/Closed Principle). | Adding a new provider requires only a new class implementing `LLMProvider`; no existing code changes needed. |
| RNF-09 | The system SHALL log all audit results and decisions to persistent storage for later review and traceability. | Audit reports remain accessible after application restart; log files are timestamped and non-repudiable. |
| RNF-10 | The system SHALL consume no more than 4 GB of additional RAM beyond the LLM model's memory requirements during audit execution. | Measured via `psutil` during a full 6-pass audit of a 50-cell notebook. |

---

## 5. Verification Plan

| Test ID | Req ID | Objective | Procedure | Expected Result | Priority |
|---|---|---|---|---|---|
| TC-01 | RF-01 | Verify local `.ipynb` loading and parsing | Call `load_notebook()` with a valid notebook, then with a malformed file. | Valid returns `Notebook(valid=True)`. Malformed returns `valid=False` with error list. | High |
| TC-02 | RF-02 | Verify GitHub URL fetch with auto-conversion | Enter `github.com/user/repo/blob/main/test.ipynb` in GitHub URL field and click Load. | URL normalised to `raw.githubusercontent.com`; notebook loads successfully. | High |
| TC-03 | RF-16 | Verify notebooks DB scanner | Click Scan DB button. | Dropdown populated with files from `notebooks/`; first valid notebook auto-loaded. | High |
| TC-04 | RF-05 | Execute all 6 audit passes on a sample notebook | Load `sample_audit.ipynb`, select all focus areas, click Run Audit. | 6 cards appear in results column; each has pass number, name, finding count, and status. | High |
| TC-05 | RF-12 | Verify hybrid evaluation (deterministic + LLM) runs without errors | Run audit with local LLM provider configured. | Deterministic checks pass without API calls; LLM-dependent passes get a result or a clear fallback message. | High |
| TC-06 | RF-15 | Export audit report in JSON format | After audit completes, click Export JSON. | Valid JSON file created at the reports path containing all pass results and metadata. | High |
| TC-07 | RF-15 | Export audit report in PDF format | After audit completes, click Export PDF. | Valid PDF file created with formatted report content. | High |
| TC-08 | RF-17 | Load notebook from manual local path | Type path to a valid `.ipynb` in Local path field and click Load Local. | Notebook loads; status shows filename and cell count. | High |
| TC-09 | RF-18 | Verify offline operation | Disconnect network, run core functions (local file load, local LLM audit). | All core functions work; cloud-only features show "unavailable" status. | Medium |
| TC-10 | RNF-04 | Start application on a machine without GPU libraries | Run `python main.py` on a system without CUDA/Metal. | App starts; GPU-dependent features show as disabled; no traceback. | Medium |
| TC-11 | RNF-06 | Verify no outbound network during local operations | Run a full audit with local LLM while monitoring network with `nethogs`. | Zero outbound connections during audit execution. | High |
| TC-12 | RNF-09 | Verify audit report persistence | Restart application after running an audit; open reports directory. | All audit reports from previous session present and readable. | Medium |
| TC-13 | RNF-10 | Verify RAM consumption during audit | Run full audit while monitoring with `psutil`. | RAM increase ≤ 4 GB above baseline (excluding LLM model allocation). | Low |

---

## 6. Justification

| Criterion | Compliance |
|---|---|
| **Problem statement** | Notebook reproducibility crisis, lack of structured audit, and absence of local-first AI tooling clearly identified with concrete failure modes (data leakage, dependency drift, hidden state). |
| **System cohesion** | Construction Framework, Audit Framework, and LLM Orchestration form a closed feedback loop: build → audit → improve. Building blocks from the Agentic AI workflow map directly to system components. |
| **Measurable, traceable requirements** | All RF and RNF are quantified with specific acceptance criteria; IDs are cross-referenced to verification tests. |
| **Architecture clarity** | Hardware and software diagrams document the current Flet desktop implementation; the provider-agnostic strategy pattern ensures extensibility. |
| **Verification plan** | 13 test cases cover all functional and key non-functional requirements with clear procedures, expected results, and priority levels. |
| **Local-first by design** | All core operations run offline with zero data egress; cloud LLM is strictly opt-in and user-initiated. |
