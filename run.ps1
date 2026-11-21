# One-step setup and launch for Windows (PowerShell).
#   powershell -ExecutionPolicy Bypass -File run.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m pip install --quiet uv
if (-not (Test-Path .venv)) { python -m uv venv .venv }
# --python .venv makes uv install into the project venv, never the system Python
python -m uv pip install --quiet --python .venv -r requirements.txt
& .\.venv\Scripts\streamlit.exe run app.py
