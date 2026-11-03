#!/usr/bin/env bash
#_launch the GUI, running setup first if the venv is missing.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo ">> No virtual environment found — running setup first ..."
    ./setup.sh
fi

VENV_PY="./.venv/bin/python"
if [ -x ./.venv/Scripts/python.exe ]; then VENV_PY="./.venv/Scripts/python.exe"; fi
exec "$VENV_PY" -X utf8 main.py "$@"
