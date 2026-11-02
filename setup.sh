#!/usr/bin/env bash
# One-time setup for Time Table Maker.
# Creates a virtual environment, installs all dependencies and generates
# a sample dataset so the GUI can be tried immediately.
set -euo pipefail
cd "$(dirname "$0")"

# ---- pick a python interpreter -------------------------------------------------
PY=""
for candidate in python3 python python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then
    echo "ERROR: Python 3 not found on PATH. Install Python 3.10+ first." >&2
    exit 1
fi

if ! "$PY" -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)"; then
    echo "ERROR: Python 3.9+ is required (found $("$PY" -V))." >&2
    exit 1
fi
echo "Using interpreter: $("$PY" -V 2>&1) ($("$PY" -c 'import sys;print(sys.executable)'))"

# ---- create the virtual environment --------------------------------------------
if [ ! -d venv ]; then
    echo ">> Creating virtual environment in ./venv ..."
    "$PY" -m venv venv
else
    echo ">> Virtual environment already exists, reusing it."
fi

# ---- install dependencies -------------------------------------------------------
echo ">> Upgrading pip ..."
./venv/bin/python -m pip install --upgrade pip --quiet
echo ">> Installing requirements (PySide6, pandas, openpyxl, ortools) ..."
./venv/bin/pip install -r requirements.txt --quiet

# ---- smoke test the engine headlessly -------------------------------------------
echo ">> Smoke-testing the engine on generated sample data ..."
./venv/bin/python create_test_data.py test_data.xlsx >/dev/null
./venv/bin/python -c "
from engine.data_loader import load_timetable_data
d = load_timetable_data('test_data.xlsx')
print(f'   ok: {len(d.subjects)} subjects, {len(d.teachers)} teachers, {len(d.classes)} classes loaded')
"

echo
echo "Setup complete. Run the app with:  ./run.sh   (or: source venv/bin/activate && python main.py)"
