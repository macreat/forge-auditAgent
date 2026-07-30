# forge-auditAgent

_Notebook Construction & Audit Framework — LLM-powered six-pass review protocol, sandboxed notebook execution, and multi-provider AI orchestration._

---

## Overview

forge-auditAgent implements the Construction Framework and Audit Framework defined in the `NotebookBuildAudit` specification: a formal methodology for authoring, executing, and systematically auditing computational notebooks (Jupyter `.ipynb`) used in machine learning and data science workflows.

The system addresses three core problems:

- **Untrusted notebook execution** — every notebook runs inside an isolated Docker sandbox with pinned dependencies, ensuring deterministic, reproducible results.
- **Lack of structured audit** — a six-pass review protocol (Structural → Reproducibility → Data Integrity → ML Correctness → Code Quality → Deployment Readiness) provides comprehensive, normalized risk scores (Low / Moderate / High) for every notebook.
- **AI-assisted review** — a hybrid LLM orchestration layer routes audit prompts to local models (Ollama / `llama.cpp`) or cloud providers (OpenAI, Anthropic, OpenCode) via a provider-agnostic strategy pattern, using three-level prompt templates (Conceptual → Methodological → Implementation).

---

## Architecture

### Construction Framework (Part I)

Three-phase build discipline for authoring new notebooks from scratch:

| Phase | Focus |
| :--- | :--- |
| **Scaffold** | Structural foundation — single-responsibility purpose, canonical eight-section headers, environment pinning, global reproducibility controls |
| **Write** | Incremental authoring — one section at a time, markdown context per code cell, explicit variable passing, versioned artifact export routing |
| **Validate During Writing** | Continuous verification — kernel restart per section, cell idempotency checks, strict linear execution order |

### Audit Framework (Part II)

Six-pass sequential review protocol — each pass delivers a scoped diagnostic:

| Pass | Scope | Deliverable |
| :--- | :--- | :--- |
| 1 — Structural Overview | Section map, purpose coherence, red flag scan | Section map + red flag list |
| 2 — Reproducibility | Dependency pinning, seeds, hardcoded paths | Risk score (L / M / H) |
| 3 — Data Integrity | Split ordering, pipeline leakage, missing data | Integrity report |
| 4 — ML Correctness | Metrics, cross-validation, tuning, baselines | Correctness checklist |
| 5 — Code Quality | Repetition threshold, dead code, naming, output hygiene | Code smell report |
| 6 — Deployment Readiness | Artifact versioning, train/inference separability, privacy | Risk score (L / M / H) |

Passes 1–2 map to **Level 1 — Conceptual**, Passes 3–4 to **Level 2 — Methodological**, and Passes 5–6 to **Level 3 — Implementation**, each with its own LLM prompt template defined in `NotebookBuildAudit.tex`.

### Feedback Loop

The Construction Framework produces a notebook artifact; the Audit Framework diagnoses it; recommendations feed back into a revised construction cycle. Notebooks entering via the audit-only path produce terminal recommendations without closing the loop.

---

## Repository Structure

```
forge-auditAgent/
├── reference/
│   ├── README.md
│   ├── docs/
│   │   ├── mds/                          # Markdown specifications
│   │   │   ├── NotebookBuildAudit.md     # Authoritative Construction & Audit Framework
│   │   │   ├── InitialProposalDev.md     # Commercial development proposal
│   │   │   ├── paperRequirementsDoc.md   # Product requirements doc (Agentic AI)
│   │   │   ├── PRD-AgenticAI-Modular.md  # 28 FRs across 8 modules
│   │   │   ├── Requirements-AgenticAI.md # SRS: 18 FRs, 10 NFRs, 13 TCs
│   │   │   └── basis.md                  # Early design notes (superseded)
│   │   ├── latex/                        # Formal LaTeX specifications
│   │   │   ├── NotebookBuildAudit.tex    # Full spec with diagrams, prompt templates
│   │   │   ├── InitialProposalDev.tex    # Commercial development proposal
│   │   │   ├── requirementsDoc/
│   │   │   │   ├── paperRequirementsDoc.tex     # Requirements paper (article class)
│   │   │   │   └── forge-auditAgent-requirements.tex  # Presentation (11pt, 19pp)
│   │   │   └── basis.tex                 # Early prompt draft iterations (superseded)
│   │   ├── pdfs/                         # Compiled PDFs
│   │   │   ├── NotebookBuildAudit.pdf
│   │   │   └── InitialProposalDev.pdf
│   │   └── imgs/
│   │       ├── prd/                      # Requirements paper diagrams
│   │       │   ├── arquitecturaAltoNivel.png
│   │       │   ├── pipelineAuditoria.png
│   │       │   └── LLMStrategyPattern.png
│   │       └── ...                        # Diagram source images
│   └── flags/
│       ├── README.md
│       └── flags.md                      # Developer task tracking
├── test/
│   ├── code/
│   │   └── conftest.py                   # Pytest configuration
│   ├── backend/                          # Notebook Audit & Construction Framework (CLI)
│   │   ├── AuditFramework/               # 6-pass audit engine (Passes 1,2,5 mechanical; 3,4,6 semantic/LLM)
│   │   ├── ConstructionFramework/        # 3-phase construction engine (Scaffold → Write → Validate)
│   │   ├── nbs/                          # Sample notebooks for testing
│   │   ├── corrections_templates.py      # 30+ structured correction templates with code examples
│   │   ├── report_generator.py           # Markdown report generator for audit/construction
│   │   ├── notebookAuditCLI.py           # Interactive CLI + batch mode
│   │   ├── QUICK_REFERENCE.md            # CLI usage reference
│   │   ├── START_HERE.md                 # Quick-start guide
│   │   └── requirements.txt              # anthropic>=0.25.0 (for semantic passes)
│   └── prompts/                          # Flet desktop app (see below)
│       ├── app/
│       │   ├── main.py                   # Dev entrypoint — launches Flet GUI
│       │   ├── launcher.py               # PyInstaller entry point (path setup + user dirs)
│       │   ├── api/
│       │   │   ├── local.py              # Hardware detection, HF model browser, GGUF download,
│       │   │   │                         #   AsyncLlamaServer (in-process LLM inference server)
│       │   │   └── utils.py              # Placeholder — future LLM provider abstraction
│       │   ├── config/
│       │   │   ├── paths.py              # Path resolution (MODELS_DIR, dev vs deploy)
│       │   │   └── settings.py           # JSON user config persistence
│       │   └── UI/
│       │       └── app.py                # Flet GUI (Hardware / Models / Server / Settings / Benchmark tabs)
│       ├── scripts/
│       │   └── install.py                # Cross-platform installer (GPU backend detection +
│       │                                 #   llama-cpp-python[server] with correct CMAKE_ARGS)
│       ├── tools/
│       │   └── hello_llm.py              # Smoke-test: chat completion to localhost:8000
│       ├── docs/                         # Sphinx documentation
│       ├── models/                       # Downloaded .gguf files land here
│       ├── templates/                    # Experiment template JSON files
│       ├── requirements.txt
│       ├── test-prompts-app.spec         # PyInstaller spec (Flet app binary)
│       │   └── test-prompts-installer.spec   # PyInstaller spec (installer binary)
├── backend/                              # Future FastAPI backend
├── frontend/                             # Future Vite + React frontend
├── .agents/
│   └── skills/                           # Reusable agent skills (flet, github-actions, etc.)
├── .github/
│   └── workflows/
│       └── release.yml                   # CI multiplatform release workflow
├── tools/
│   └── install_agent_tools.sh            # System dependency installer
├── logs/
├── requirements.txt                      # Root-level pip requirements
├── AGENTS.md                             # Agent onboarding & repo guide
└── README.md                             # This file
```

---

## test/prompts/ — Desktop GUI (Flet)

A cross-platform desktop app built with Python 3.14 and Flet that detects your hardware, queries HuggingFace for suitable GGUF models, lets you pick a quantization, downloads a single `.gguf` file, and serves it via a local OpenAI-compatible HTTP API — all through a graphical interface.

### Install

```bash
cd test/prompts
venv/bin/python3 scripts/install.py
```

The installer detects your GPU backend (Metal on macOS, CUDA, or ROCm) and compiles `llama-cpp-python[server]` with the correct flags.

### Run

```bash
cd test/prompts
venv/bin/python3 app/main.py
```

**GUI tabs:** Hardware Info → Model Browser (HuggingFace GGUF search with param-count filter) → Quantization Picker (with file sizes) → Download → Local Server (start/stop with nGpuLayers and nCtx controls) → Benchmark (side-by-side prompt testing across local .gguf models and external APIs).

### PyInstaller builds

```bash
cd test/prompts
pip install pyinstaller
pyinstaller test-prompts-app.spec        # Flet GUI binary
pyinstaller test-prompts-installer.spec  # CLI installer binary
```

### CI/CD

Push a `test-prompts/v*` tag to trigger the multiplatform release workflow (`.github/workflows/release.yml`) — builds PyInstaller binaries on Linux, macOS, and Windows and publishes them to GitHub Releases.

### Multi-OS GPU acceleration

| OS | Backend | Detection |
|----|---------|-----------|
| macOS | Metal | Always available |
| Linux | CUDA / ROCm | nvidia-smi → rocm-smi |
| Windows | CUDA | nvidia-smi |

### AsyncLlamaServer

In-process local LLM server using `llama-cpp-python[server]`. Serve any `.gguf` model via an OpenAI-compatible HTTP API:

```python
from app.api.local import AsyncLlamaServer

server = AsyncLlamaServer("models/model.gguf", port=8000, nGpuLayers=-1)
await server.start()   # launches in background
# ... use the API at http://127.0.0.1:8000 ...
await server.stop()
```

### Docs

Separate Sphinx venv at `docs/venv/`. Build with:

```bash
cd test/prompts
LC_ALL=C.UTF-8 docs/venv/bin/python3 -m sphinx -b html docs docs/_build -W
```

Dependencies: `huggingface_hub`, `psutil`, `GPUtil`, `llama-cpp-python[server]`, `ollama`. See `test/prompts/requirements.txt`.

---

## test/backend/ — Notebook Audit & Construction Framework (CLI)

CLI tool implementing the 6-pass Audit Framework and 3-phase Construction Framework from the reference specifications (`reference/docs/mds/NotebookBuildAudit.md`).

### Quick Start

```bash
cd test/backend

# Interactive mode (menu-driven)
python notebookAuditCLI.py

# Or specific pass/phase
python notebookAuditCLI.py --mode audit --notebook nbs/test_notebook.ipynb --pass 1
python notebookAuditCLI.py --mode construction --notebook nbs/test_notebook.ipynb --phase 1

# List available notebooks
python notebookAuditCLI.py --list
```

### Dependencies

- `test/backend/requirements.txt` — `anthropic>=0.25.0`
- **Only required for semantic passes (3, 4, 6)** — Mechanical passes (1, 2, 5) use stdlib only

### Features

| Component | Passes/Phases | Description |
|-----------|---------------|-------------|
| **Audit Engine** | 1, 2, 5 (mechanical) | Structural Overview, Reproducibility, Code Quality — AST/JSON parsing only |
| **Audit Engine** | 3, 4, 6 (semantic) | Data Integrity, ML Correctness, Deployment Readiness — LLM prompt templates ready |
| **Construction Engine** | 1, 2, 3 | Scaffold → Write → Validate — checklist-driven with gate decisions |
| **Reports** | — | Timestamped Markdown in `test/backend/outDir/` |
| **Corrections** | — | 30+ templates with bad/good code examples and severity |

### Sample Notebooks

`test/backend/nbs/` — `hc-rf-1.ipynb`, `test_notebook.ipynb`

### Reports Generated

```
audit_report_<notebook>_pass<1-6>_<timestamp>.md
construction_report_<notebook>_phase<1-3>_<timestamp>.md
```

Each report includes: issues summary (sorted by severity), detailed corrections with code examples, gate decision (PROCEED/PROCEED_WITH_WARNINGS/BLOCK), and checklist.

---

## Proposed Technology Stack

From `InitialProposalDev.md` — the implementation plan targets:

| Layer | Technology |
| :--- | :--- |
| **Backend** | Python 3.11+ / FastAPI (async REST + SSE streaming) |
| **Frontend** | Vite + React 18 + TypeScript |
| **AI / LLM** | Ollama + `llama.cpp` (local) / OpenAI + Anthropic + OpenCode (cloud) — provider-agnostic strategy pattern |
| **Notebook Runtime** | `@jupyter-kit` — programmatic kernel management inside Docker sandboxes |
| **Database** | PostgreSQL 15 + SQLAlchemy 2.0 (async) + Alembic migrations |
| **Infrastructure** | Docker + Docker Compose — fully containerized, per-notebook isolation |

---

## Development Roadmap

| Phase | Duration | Focus |
| :--- | :--- | :--- |
| Phase 1 — Foundation | 2 weeks | Docker sandboxes, `@jupyter-kit` integration, environment pinning |
| Phase 2 — Backend & AI | 4 weeks | FastAPI API, six-pass audit state machine, LLM provider strategy |
| Phase 3 — Frontend | 3 weeks | Vite + React dashboard, real-time audit logs, provider routing UI |
| Phase 4 — QA & Deploy | 2 weeks | Integration testing, Docker Compose deployment, documentation |

**Total: 11 weeks**

---

## Key Reference Documents

- [NotebookBuildAudit.md](reference/docs/mds/NotebookBuildAudit.md) — complete Construction and Audit Framework specification
- [NotebookBuildAudit.tex](reference/docs/latex/NotebookBuildAudit.tex) — formal LaTeX with diagrams and prompt templates
- [paperRequirementsDoc.md](reference/docs/mds/paperRequirementsDoc.md) — product requirements doc (Agentic AI protocol, 20 sections)
- [paperRequirementsDoc.tex](reference/docs/latex/requirementsDoc/paperRequirementsDoc.tex) — LaTeX compilation, article-class, diagram placeholders
- [forge-auditAgent-requirements.tex](reference/docs/latex/requirementsDoc/forge-auditAgent-requirements.tex) — requirements presentation, 11pt, 19pp
- [PRD-AgenticAI-Modular.md](reference/docs/mds/PRD-AgenticAI-Modular.md) — standalone PRD with 28 FRs across 8 modules
- [Requirements-AgenticAI.md](reference/docs/mds/Requirements-AgenticAI.md) — SRS with 18 FRs, 10 NFRs, 13 TCs
- [InitialProposalDev.md](reference/docs/mds/InitialProposalDev.md) — commercial development proposal
- [AGENTS.md](AGENTS.md) — agent onboarding and repo guide
- [flags.md](reference/flags/flags.md) — developer task tracking

---

## Repo Status

This is a design/documentation project with an active prototype. Runnable code lives in `test/prompts/` (see above) — a working Flet desktop GUI for hardware detection, GGUF model download, and local LLM inference. A CLI audit/construction framework lives in `test/backend/`. Product requirements documents (20-section paper, PRD with 28 FRs, SRS with 18 FRs + 10 NFRs + 13 TCs) are published under `reference/docs/`. Sphinx documentation is set up under `test/prompts/docs/`. CI/CD is configured via GitHub Actions (`test-prompts/v*` tags trigger multiplatform PyInstaller builds). No linting or test suite yet. Full-stack implementation roadmap is outlined below.

---

## License

Proprietary — commercial in confidence. Licensing terms to be determined upon project commencement.
