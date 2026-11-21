#!/usr/bin/env sh
# One-step setup and launch for macOS / Linux:  ./run.sh
set -e
cd "$(dirname "$0")"
command -v uv >/dev/null 2>&1 || python3 -m pip install --quiet uv
[ -d .venv ] || python3 -m uv venv
python3 -m uv pip install --quiet -r requirements.txt
exec .venv/bin/streamlit run app.py
