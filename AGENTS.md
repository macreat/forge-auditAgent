# AGENTS.md — forge-auditAgent

## Repo status

The root is a design/documentation project. Runnable code lives in `test/prompts/` (Python CLI app). No CI, no lint/format/typecheck configs, no test suite, no package manager at root.

## Working code: `test/prompts/`

Self-contained Python 3.14 app with its own venv. Desktop GUI (Flet) to detect hardware, query HuggingFace for suitable GGUF models, let the user pick a quantization, download a single `.gguf` file, and serve it via a local OpenAI-compatible HTTP API.

- **Run:** `cd test/prompts && venv/bin/python3 app/main.py`
- **Install:** `cd test/prompts && venv/bin/python3 scripts/install.py`
- **Test server:** `cd test/prompts && venv/bin/python3 tools/hello_llm.py`
- **Deps:** `test/prompts/requirements.txt` (flet, huggingface_hub, psutil, GPUtil, ollama, httpx, oauthlib, llama-cpp-python[server])
- **App venv:** `test/prompts/venv/` — Python 3.14.4, created via `python3 -m venv`

```
test/prompts/
├── app/
│   ├── __init__.py             # Package marker
│   ├── main.py                 # Dev entrypoint — launches the Flet GUI
│   ├── launcher.py             # PyInstaller entry point (path setup + user dirs)
│   ├── api/
│   │   ├── __init__.py         # Package marker
│   │   ├── local.py            # checkHardware, haveGpuAccel, listAvailableModels,
│   │   │                       #   listAvailableQuantizations, downloadSelectedModel,
│   │   │                       #   AsyncLlamaServer (in-process LLM server via llama-cpp-python)
│   │   └── utils.py            # Placeholder — future LLM provider abstraction
│   ├── config/
│   │   ├── __init__.py         # Package marker
│   │   ├── paths.py            # MODELS_DIR, defaultModelsDir (dev vs deploy), isDeployed
│   │   └── settings.py         # JSON user config (~/.test-prompts/config.json)
│   └── UI/
│       ├── __init__.py         # Package marker
│       └── app.py              # Flet GUI (Hardware / Models / Server / Settings tabs)
├── scripts/
│   ├── __init__.py             # Package marker
│   └── install.py              # Cross-platform installer — detects GPU backend, installs
│                               #   llama-cpp-python[server] with correct CMAKE_ARGS
├── tools/
│   └── hello_llm.py            # Smoke-test: sends chat completion to localhost:8000
├── docs/
│   ├── README.md               # Docs build instructions
│   ├── requirements.txt        # sphinx, sphinx-rtd-theme
│   ├── venv/                   # Isolated docs venv (separate from app venv)
│   ├── conf.py                 # Sphinx config (autodoc, napoleon, RTD theme, mock imports)
│   ├── index.rst               # Main toctree
│   └── app.*.rst               # Per-module doc pages
├── models/                     # Downloaded .gguf files land here (dev) or ~/.test-prompts/models (deploy)
├── notebooks/ (empty)
├── requirements.txt
└── venv/
```

### App flow (main.py)

1. `haveGpuAccel()` → `bool` — detects Metal (macOS), CUDA (nvidia-smi), or ROCm (rocm-smi)
2. `checkHardware()` → dict with OS, RAM, GPU, recommendation (`size` float, `mode` "cpu"/"gpu")
3. `listAvailableModels(hardwareDict)` → `list[str]` of GGUF model IDs from HuggingFace matching param count
4. `listAvailableQuantizations(modelId)` → `dict[str, float]` of `{quant_name: size_mb}`
5. `downloadSelectedModel(modelId, quantization)` → downloads single gguf to `defaultModelsDir()/`

### AsyncLlamaServer (local.py)

In-process local LLM server using `llama-cpp-python[server]` + `uvicorn`. Constructor accepts `modelPath`, `host`, `port`, `nGpuLayers` (-1 for all GPU layers, 0 for CPU), `nCtx`. Use `start()` to launch the server as a background asyncio task, `stop()` to shut it down gracefully.

### Dev vs deploy paths

`config/paths.py` provides `defaultModelsDir()` — returns the project-local `models/` when running from source (`sys.frozen` is falsy), or `~/.test-prompts/models/` when packaged with PyInstaller. The GUI model dropdown and download target both respect this.

### Multi-OS GPU support

| OS | Backend | Detection |
|----|---------|-----------|
| macOS | Metal | Always available |
| Linux | CUDA / ROCm | nvidia-smi → rocm-smi |
| Windows | CUDA | nvidia-smi |

### Key dependencies

- `huggingface_hub` — `HfApi.list_models`, `list_repo_files`, `get_paths_info`, `hf_hub_download`
- `psutil`, `GPUtil` — hardware detection (optional; graceful fallback on ImportError)
- `llama-cpp-python[server]` — in-process GGUF inference server (installed by `scripts/install.py` with platform-specific CMAKE_ARGS)

### Docs

Separate Sphinx venv at `docs/venv/`. Build with:

```bash
cd test/prompts
LC_ALL=C.UTF-8 docs/venv/bin/python3 -m sphinx -b html docs docs/_build -W
```

See `docs/README.md` for full setup instructions.

## Design & Reference (root-level)

- `reference/docs/mds/NotebookBuildAudit.md` — authoritative Construction Framework and Audit Framework
- `reference/docs/latex/NotebookBuildAudit.tex` — formal LaTeX spec with diagrams and prompt templates
- `reference/docs/mds/basis.md` — early design notes (superseded by NotebookBuildAudit.md)
- `reference/docs/latex/basis.tex` — early LaTeX notes (superseded by NotebookBuildAudit.tex)
- `reference/docs/InitialProposalDev.md` / `.tex` / `.pdf` — commercial development proposal
- `reference/docs/InitialProposalDev.tex` compiles via `latexmk -pdf && latexmk -c`

## Project Management

- `reference/flags/flags.md` — developer task tracking
- `.agents/skills/` — reusable agent skills
- `tools/` — root-level scripts; currently contains `install_agent_tools.sh`

## Repo quirks

- `.skills/` and `.tools/` existed in git history but were reorganized. Do not recreate them.
- Root `README.md` is stale — it claims no runnable code exists, but `test/prompts/` is a working app.
- `hf_hub_download` creates a `.cache/huggingface/` dir inside `MODELS_DIR`; this is expected, not garbage.
- `scripts/` was originally named `cmd/` but had to be renamed — `cmd` shadows Python's stdlib `cmd` module.
- Docs use `autodoc_mock_imports` to avoid pulling in the full app venv's dependencies at build time.
