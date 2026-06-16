$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Development environment was not found at '$pythonExe'."
}

Set-Location $projectRoot

& $pythonExe -m uvicorn services.api.main:app `
    --host 127.0.0.1 `
    --port 8000 `
    --reload `
    --proxy-headers `
    --forwarded-allow-ips 127.0.0.1
