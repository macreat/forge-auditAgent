# Docs

Sphinx documentation with ReadTheDocs theme and Google-style autodoc.

## Setup

```bash
cd test/prompts
python3 -m venv docs/venv
docs/venv/bin/pip install -r docs/requirements.txt
```

## Build

```bash
cd test/prompts
LC_ALL=C.UTF-8 docs/venv/bin/python3 -m sphinx -b html docs docs/_build -W
```

Output lands in `docs/_build/`. Open `docs/_build/index.html` in a browser.

## Structure

```
docs/
├── conf.py              # Sphinx config (autodoc, napoleon, RTD theme, mock imports)
├── index.rst            # Main toctree
├── requirements.txt     # sphinx, sphinx-rtd-theme
├── venv/                # Isolated Python venv (git-ignored)
├── app.*.rst            # Per-module docs
├── scripts.install.rst  # Installer docs
└── _build/              # Generated HTML (git-ignored)
```

## Notes

- The docs venv is separate from the app venv (`venv/`). Only Sphinx deps are installed here.
- External Python deps (`huggingface_hub`, `psutil`, `llama_cpp`) are mocked via `autodoc_mock_imports` in `conf.py` so autodoc can build without the full app environment.
- The `-W` flag treats warnings as errors. Remove it for development builds.
