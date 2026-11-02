#!/usr/bin/env bash
#_launch the GUI, running setup first if the venv is missing.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d venv ]; then
    echo ">> No virtual environment found — running setup first ..."
    ./setup.sh
fi

exec ./venv/bin/python main.py "$@"
