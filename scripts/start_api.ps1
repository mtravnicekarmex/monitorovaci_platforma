$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment nebyl nalezen v .venv. Vytvor ho pres 'py -m venv .venv' a doinstaluj requirements-api.txt."
}

Set-Location $projectRoot

& $pythonExe -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --reload
