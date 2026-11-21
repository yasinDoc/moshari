# One-step setup and launch for Windows (PowerShell).
#   powershell -ExecutionPolicy Bypass -File run.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { python -m pip install --quiet uv }
if (-not (Test-Path .venv)) { python -m uv venv }
python -m uv pip install --quiet -r requirements.txt
& .\.venv\Scripts\streamlit.exe run app.py
