import os
import sys

sys.path.insert(0, os.path.abspath(".."))

autodoc_mock_imports = [
    "huggingface_hub",
    "psutil",
    "GPUtil",
    "GPUtil.getGPUs",
    "llama_cpp",
    "llama_cpp.server",
    "llama_cpp.server.app",
    "llama_cpp.server.settings",
    "uvicorn",
    "flet",
    "aiohttp",
]

project = "test-prompts-app"
copyright = "2026"
author = "test-prompts-app contributors"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.autosummary",
]

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "venv", "venv/**"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
