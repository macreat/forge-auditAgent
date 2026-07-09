# test-prompts-app

Cross-platform desktop app for hardware detection, GGUF model download, and local LLM inference. Built with Python 3.14, Flet, llama-cpp-python, and HuggingFace Hub.

---

## Quick start (from source)

```bash
# 1. Clone the repo
git clone <repo-url>
cd forge-auditAgent/test/prompts

# 2. Create app venv
python3 -m venv venv

# 3. Run the installer (detects GPU, installs deps with correct flags)
venv/bin/python3 scripts/install.py

# 4. Launch the app
venv/bin/python3 app/main.py
```

The installer detects your GPU backend (Metal on macOS, CUDA, or ROCm) and compiles llama-cpp-python with the correct `CMAKE_ARGS`.

---

## Usage

### GUI

The app opens a desktop window with four tabs:

- **Hardware** — OS, RAM, GPU info, and model size recommendation
- **Models** — browse HuggingFace for compatible GGUF models, pick a quantization, download to disk
- **Server** — select a downloaded model from a dropdown (or type a path), configure host/port/GPU layers/context, start/stop the local inference server
- **Settings** — change models directory, save config

The Server tab shows all `.gguf` files in the models directory in a dropdown. Use **Refresh** to rescan after new downloads.

### Smoke-test the server

After starting the server, verify it works:

```bash
venv/bin/python3 tools/hello_llm.py
```

Sends a chat-completion request to `http://localhost:8000/v1/chat/completions` and prints the reply.

---

## Dev vs deploy modes

The models directory depends on how the app is launched:

| Mode       | Detection              | Models directory              |
|-----------|------------------------|-------------------------------|
| Dev       | `sys.frozen` is falsy  | `test/prompts/models/`        |
| Deploy    | PyInstaller (frozen)   | `~/.test-prompts/models/`     |

Override with the `TEST_PROMPTS_HOME` environment variable.

---

## Build standalone executables

Two PyInstaller binaries can be built for distribution:

### App binary (Flet GUI, 57 MB, CPU-only llama-cpp)

```bash
venv/bin/pip install pyinstaller
venv/bin/pyinstaller test-prompts-app.spec
# output: dist/test-prompts-app
```

### Installer binary (9 MB, creates venv + GPU-accelerated deps)

```bash
venv/bin/pyinstaller test-prompts-installer.spec
# output: dist/test-prompts-installer
```

---

## User flow (binary distribution)

```bash
# Step 1 — download the installer binary for your OS
./test-prompts-installer          # creates venv/, installs deps with GPU support

# Step 2 — run the app
venv/bin/python3 app/main.py      # or use the bundled test-prompts-app binary
```

---

## Project structure

```
test/prompts/
├── app/
│   ├── main.py              # Dev entry point → launches Flet UI
│   ├── launcher.py          # PyInstaller entry point (path setup + user dirs)
│   ├── api/
│   │   ├── local.py         # Hardware detection, HF model browser, GGUF download,
│   │   │                    #   AsyncLlamaServer (in-process LLM inference server)
│   │   └── utils.py         # Placeholder — future LLM provider abstraction
│   ├── config/
│   │   ├── paths.py         # Filesystem paths (dev vs deploy, defaultModelsDir)
│   │   └── settings.py      # JSON settings persistence
│   └── UI/
│       └── app.py           # Flet GUI (Hardware / Models / Server / Settings tabs)
├── scripts/
│   └── install.py           # Cross-platform GPU-aware installer
├── tools/
│   └── hello_llm.py         # Quick smoke-test for the local LLM server
├── docs/
│   ├── README.md            # Docs build instructions
│   ├── requirements.txt     # Sphinx deps
│   ├── venv/                # Isolated docs venv (git-ignored)
│   ├── conf.py              # Sphinx config
│   └── *.rst                # Per-module autodoc pages
├── models/                  # Downloaded .gguf files (git-ignored)
├── notebooks/               # Empty, reserved for future use
├── requirements.txt         # App Python dependencies
├── test-prompts-app.spec    # PyInstaller spec — bundles the Flet app
└── test-prompts-installer.spec # PyInstaller spec — bundles the installer
```

---

## Docs

Build Sphinx documentation:

```bash
# Setup
python3 -m venv docs/venv
docs/venv/bin/pip install -r docs/requirements.txt

# Build
LC_ALL=C.UTF-8 docs/venv/bin/python3 -m sphinx -b html docs docs/_build -W
```

Open `docs/_build/index.html` in a browser.

---

## User config

Settings are stored in `~/.test-prompts/config.json`:

```json
{
  "host": "127.0.0.1",
  "port": 8000,
  "nGpuLayers": 0,
  "nCtx": 2048,
  "modelsDir": "/path/to/models",
  "lastModelPath": ""
}
```

---

## Multi-OS GPU support

| OS | Backend | Detection |
|----|---------|-----------|
| macOS | Metal | Always available |
| Linux | CUDA / ROCm | nvidia-smi → rocm-smi |
| Windows | CUDA | nvidia-smi |

Use `nGpuLayers=-1` for full GPU offload, `nGpuLayers=0` for CPU-only.

---

## API reference

### Hardware detection

```python
from app.api.local import checkHardware, haveGpuAccel

hw = checkHardware()
# {'os': {...}, 'systemRam': {...}, 'gpu': {...}, 'recommendation': {...}}

haveGpuAccel()  # True if CUDA/ROCm/Metal available
```

### Model download

```python
from app.api.local import listAvailableModels, listAvailableQuantizations, downloadSelectedModel

models = listAvailableModels(hw)                # [str] of model IDs
quants = listAvailableQuantizations(models[0])   # {quant_name: size_mb}
path = downloadSelectedModel(models[0], "Q4_K_M")  # downloads to models/
```

### Local inference server

```python
from app.api.local import AsyncLlamaServer

server = AsyncLlamaServer("models/model.gguf", port=8000, nGpuLayers=-1)
await server.start()    # serves at http://127.0.0.1:8000 (OpenAI-compatible)
# ... use the API ...
await server.stop()
```
