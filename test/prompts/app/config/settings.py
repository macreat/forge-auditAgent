"""User settings persistence via JSON config file."""

import json
import os
from pathlib import Path
from app.config.paths import userConfigPath, ensureUserDirs, defaultModelsDir, defaultReportsDir

_DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8000,
    "nGpuLayers": 0,
    "nCtx": 2048,
    "modelsDir": str(defaultModelsDir()),
    "reportsDir": str(defaultReportsDir()),
    "lastModelPath": "",
    "llmProvider": "local",
    "openaiApiKey": "",
    "anthropicApiKey": "",
    "ollamaModel": "llama3.2",
}


def load():
    ensureUserDirs()
    path = userConfigPath()
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            merged = {**_DEFAULTS, **data}
            merged["modelsDir"] = data.get("modelsDir", _DEFAULTS["modelsDir"])
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULTS)


def save(settings):
    ensureUserDirs()
    path = userConfigPath()
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
    _restrictConfigPermissions(path)


def _restrictConfigPermissions(path):
    """Enforce owner-only permissions (0o600) on the config file.

    The config stores API keys (``openaiApiKey``, ``anthropicApiKey``), so
    it must not be readable by other users. Best-effort: filesystems
    without POSIX permissions raise OSError, which is ignored to preserve
    the save behavior.
    """
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
