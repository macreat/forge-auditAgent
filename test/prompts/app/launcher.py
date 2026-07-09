"""PyInstaller entry point for test-prompts-app.

When running as a PyInstaller bundle, performs first-run setup
(user directory creation, config initialization), then launches the Flet UI.

Can also be run directly during development:
    python3 app/launcher.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.paths import ensureUserDirs

if __name__ == "__main__":
    ensureUserDirs()
    from app.UI.app import main

    main()
