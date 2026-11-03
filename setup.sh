#!/usr/bin/env bash
# One-time setup for Time Table Maker.
# Creates a virtual environment, installs all dependencies and generates
# a sample dataset so the GUI can be tried immediately.
set -euo pipefail
cd "$(dirname "$0")"

# ---- pick a python interpreter -------------------------------------------------
PY=""
for candidate in python3 python python3.14 python3.13 python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then
    echo "ERROR: Python 3 not found on PATH. Install Python 3.11+ first." >&2
    exit 1
fi

if ! "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"; then
    echo "ERROR: Python 3.11+ is required (found $("$PY" -V))." >&2
    exit 1
fi
echo "Using interpreter: $("$PY" -V 2>&1) ($("$PY" -c 'import sys;print(sys.executable)'))"

# ---- create the virtual environment --------------------------------------------
if [ ! -d .venv ]; then
    echo ">> Creating virtual environment in ./.venv ..."
    "$PY" -m venv .venv
else
    echo ">> Virtual environment already exists, reusing it."
fi

# ---- install dependencies -------------------------------------------------------
VENV_PY="./.venv/bin/python"
if [ -x ./.venv/Scripts/python.exe ]; then VENV_PY="./.venv/Scripts/python.exe"; fi
echo ">> Installing requirements (PySide6, pandas, openpyxl, ortools) ..."
"$VENV_PY" -m pip install -r requirements.txt

# ---- smoke test the engine headlessly -------------------------------------------
echo ">> Running regression checks (including a real solver run) ..."
"$VENV_PY" -X utf8 -m unittest discover -s tests -v

echo
echo "Setup complete. Run the app with: ./run.sh"
