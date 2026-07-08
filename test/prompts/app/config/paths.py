# paths
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent
APP_DIR = CONFIG_DIR.parent
ROOT_DIR = APP_DIR.parent

MODELS_DIR = ROOT_DIR / "models"
NOTEBOOKS_DIR = ROOT_DIR / "notebooks"

def debugPaths():
    print(f"CONFIG_DIR: {CONFIG_DIR}")
    print(f"APP_DIR: {APP_DIR}")
    print(f"ROOT_DIR: {ROOT_DIR}")
    print(f"MODELS_DIR: {MODELS_DIR}")
    print(f"NOTEBOOKS_DIR: {NOTEBOOKS_DIR}")
