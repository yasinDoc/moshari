#!/usr/bin/env sh
# One-step setup and launch for macOS / Linux:  ./run.sh
set -e
cd "$(dirname "$0")"
python3 -m pip install --quiet uv
[ -d .venv ] || python3 -m uv venv .venv
# --python .venv makes uv install into the project venv, never the system Python
python3 -m uv pip install --quiet --python .venv -r requirements.txt
exec .venv/bin/streamlit run app.py
