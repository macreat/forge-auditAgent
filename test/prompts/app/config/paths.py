"""Project-wide filesystem paths.

All directory constants are resolved relative to this file's location
for development, and relative to $HOME for deployed installs.
"""

import sys
import os
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent
APP_DIR = CONFIG_DIR.parent
ROOT_DIR = APP_DIR.parent

MODELS_DIR = ROOT_DIR / "models"
NOTEBOOKS_DIR = ROOT_DIR / "notebooks"

_USER_BASE = Path(os.environ.get("TEST_PROMPTS_HOME", Path.home() / ".test-prompts"))


def isDeployed():
    return getattr(sys, "frozen", False)


def defaultModelsDir():
    if isDeployed():
        return userModelsDir()
    return MODELS_DIR


def userModelsDir():
    return _USER_BASE / "models"


def userConfigPath():
    return _USER_BASE / "config.json"


def userVenvDir():
    return _USER_BASE / "venv"


def ensureUserDirs():
    _USER_BASE.mkdir(parents=True, exist_ok=True)
    userModelsDir().mkdir(parents=True, exist_ok=True)


def debugPaths():
    print(f"CONFIG_DIR: {CONFIG_DIR}")
    print(f"APP_DIR: {APP_DIR}")
    print(f"ROOT_DIR: {ROOT_DIR}")
    print(f"MODELS_DIR: {MODELS_DIR}")
    print(f"NOTEBOOKS_DIR: {NOTEBOOKS_DIR}")
    print(f"USER_BASE: {_USER_BASE}")
    print(f"USER_MODELS: {userModelsDir()}")
    print(f"USER_CONFIG: {userConfigPath()}")
    print(f"USER_VENV: {userVenvDir()}")
