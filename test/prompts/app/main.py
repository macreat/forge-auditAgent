"""Development entry point for test-prompts-app.

Runs the Flet UI directly. Requires the project venv to be set up with
all dependencies installed (see scripts/install.py).
"""

import sys
import os

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.UI.app import main

if __name__ == "__main__":
    main()
