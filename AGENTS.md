# AGENTS.md — forge-auditAgent

## Repo status

The root is a design/documentation project. Runnable code lives in `test/prompts/` (Python CLI app). No CI, no lint/format/typecheck configs, no test suite, no package manager at root.

## Working code: `test/prompts/`

Self-contained Python 3.14 app with its own venv. Acts as a CLI tool to detect hardware, query HuggingFace for suitable GGUF models, let the user pick a quantization, and download a single `.gguf` file.

- **Run:** `cd test/prompts && venv/bin/python3 app/main.py`
- **Deps:** `test/prompts/requirements.txt` (flet, huggingface_hub, psutil, GPUtil, ollama, httpx, oauthlib)
- **Venv:** `test/prompts/venv/` — Python 3.14.4, created via `python3 -m venv`

```
test/prompts/
├── app/
│   ├── main.py               # CLI entrypoint — hardware check → model list → quant pick → download
│   ├── api/
│   │   ├── local.py          # checkHardware, listAvailableModels, listAvailableQuantizations, downloadSelectedModel
│   │   └── utils.py          # Placeholder — future LLM provider abstraction
│   ├── config/paths.py       # MODELS_DIR / NOTEBOOKS_DIR resolved relative to ROOT_DIR
│   └── UI/utils.py           # Placeholder UI module
├── models/                   # Downloaded .gguf files land here flat (not in subdirs)
├── notebooks/ (empty)
├── requirements.txt
└── venv/
```

### App flow (main.py)

1. `checkHardware()` → dict with OS, RAM, GPU, recommendation (`size` float, `mode` "cpu"/"gpu")
2. `listAvailableModels(hardwareDict)` → `list[str]` of GGUF model IDs from HuggingFace matching param count
3. `listAvailableQuantizations(modelId)` → `dict[str, float]` of `{quant_name: size_mb}`
4. `downloadSelectedModel(modelId, quantization)` → downloads single gguf to `MODELS_DIR/`

### Key dependencies

- `huggingface_hub` — `HfApi.list_models`, `list_repo_files`, `get_paths_info`, `hf_hub_download`
- `psutil`, `GPUtil` — hardware detection (optional; graceful fallback on ImportError)

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
- `tools/` — reserved for future tooling; currently empty

## Repo quirks

- `.skills/` and `.tools/` existed in git history but were reorganized. Do not recreate them.
- Root `README.md` is stale — it claims no runnable code exists, but `test/prompts/` is a working app.
- `hf_hub_download` creates a `.cache/huggingface/` dir inside `MODELS_DIR`; this is expected, not garbage.
