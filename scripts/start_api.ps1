$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv-production\Scripts\python.exe"
$verifyScript = Join-Path $projectRoot "scripts\verify_production_environment.py"
$logRunner = Join-Path $projectRoot "scripts\run_with_rotating_log.py"

foreach ($requiredPath in @($pythonExe, $verifyScript, $logRunner)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required production file was not found: $requiredPath"
    }
}

Set-Location $projectRoot
& $pythonExe $verifyScript
if ($LASTEXITCODE -ne 0) {
    throw "Production environment does not match requirements-production.lock.txt."
}

& $pythonExe $logRunner --log-name api -- $pythonExe `
    -m uvicorn services.api.main:app `
    --host 127.0.0.1 `
    --port 8000 `
    --workers 1 `
    --proxy-headers `
    --forwarded-allow-ips 127.0.0.1
