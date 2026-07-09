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
│   ├── docs/
│   │   ├── mds/                          # Markdown specifications
│   │   │   ├── NotebookBuildAudit.md     # Authoritative Construction & Audit Frameworks
│   │   │   └── basis.md                  # Early design notes (superseded)
│   │   ├── latex/                        # Formal LaTeX specifications
│   │   │   ├── NotebookBuildAudit.tex    # Full spec with diagrams, prompt templates, structural trees
│   │   │   └── basis.tex                 # Early prompt draft iterations (superseded)
│   │   ├── pdfs/                         # Compiled PDFs
│   │   ├── imgs/                         # Diagram source images
│   │   ├── InitialProposalDev.md         # Commercial development proposal (Markdown)
│   │   ├── InitialProposalDev.tex        # Commercial development proposal (LaTeX)
│   │   └── InitialProposalDev.pdf        # Commercial development proposal (PDF)
│   └── flags/
│       └── flags.md                      # Developer task tracking
├── test/prompts/                         # Working CLI app (see below)
│   ├── app/
│   │   ├── main.py                       # Entrypoint — hardware check → model download
│   │   ├── api/
│   │   │   ├── local.py                  # Hardware detection, HF model browser, GGUF download,
│   │   │   │                             #   AsyncLlamaServer (in-process LLM inference server)
│   │   │   └── utils.py                  # Placeholder — future LLM provider abstraction
│   │   ├── config/
│   │   │   └── paths.py                  # Path resolution (MODELS_DIR, NOTEBOOKS_DIR)
│   │   └── UI/
│   │       └── utils.py                  # Placeholder UI module
│   ├── scripts/
│   │   └── install.py                    # Cross-platform installer (GPU backend detection + 
│   │                                     #   llama-cpp-python[server] with correct CMAKE_ARGS)
│   ├── docs/
│   │   ├── README.md                     # Docs build instructions
│   │   ├── requirements.txt              # sphinx, sphinx-rtd-theme
│   │   ├── venv/                         # Isolated docs venv
│   │   ├── conf.py                       # Sphinx config (autodoc, napoleon, RTD theme)
│   │   ├── index.rst                     # Main toctree
│   │   └── app.*.rst                     # Per-module autodoc pages
│   ├── models/                           # Downloaded .gguf files land here
│   ├── templates/                        # Experiment template JSON files
│   └── requirements.txt                  # Python 3.14 venv dependencies
├── .agents/
│   └── skills/
├── tools/                                # Future tooling
├── AGENTS.md                             # Agent onboarding & repo guide
└── README.md                             # This file
```

---

## test/prompts/ — Working CLI

A self-contained Python 3.14 CLI tool that auto-selects and downloads GGUF models matching your hardware, and serves them via a local OpenAI-compatible HTTP API.

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

**Flow:** hardware detection → HuggingFace model search (GGUF only, regex-filtered by param count) → quantization pick (with file sizes) → single `.gguf` download to `models/`.

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
- [InitialProposalDev.md](reference/docs/InitialProposalDev.md) — commercial development proposal
- [AGENTS.md](AGENTS.md) — agent onboarding and repo guide
- [flags.md](reference/flags/flags.md) — developer task tracking

---

## Repo Status

This is a design/documentation project with an active prototype. Runnable code lives in `test/prompts/` (see above) — a working CLI for hardware detection, GGUF model download, and local LLM inference. Sphinx documentation is set up under `test/prompts/docs/`. No CI/CD, linting, or test suite yet. Full-stack implementation roadmap is outlined below.

---

## License

Proprietary — commercial in confidence. Licensing terms to be determined upon project commencement.
