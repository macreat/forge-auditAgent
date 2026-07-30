#!/usr/bin/env bash
# run.sh — launch the test-prompts Flet app
# Suppresses harmless WSL graphics driver warnings (EGL/MESA/ZINK/GDK).
set -euo pipefail
cd "$(dirname "$0")"

export LIBGL_ALWAYS_SOFTWARE=1
exec venv/bin/python3 app/main.py 2>/dev/null
