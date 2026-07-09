"""User settings persistence via JSON config file."""

import json
from pathlib import Path
from app.config.paths import userConfigPath, ensureUserDirs, defaultModelsDir

_DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8000,
    "nGpuLayers": 0,
    "nCtx": 2048,
    "modelsDir": str(defaultModelsDir()),
    "lastModelPath": "",
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
    with open(userConfigPath(), "w") as f:
        json.dump(settings, f, indent=2)
