param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonVersion = "3.14"
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$environmentPath = Join-Path $resolvedProjectRoot ".venv-production"
$pythonExe = Join-Path $environmentPath "Scripts\python.exe"
$lockPath = Join-Path $resolvedProjectRoot "requirements-production.lock.txt"
$verifyScript = Join-Path $resolvedProjectRoot "scripts\verify_production_environment.py"

if (Test-Path -LiteralPath $environmentPath) {
    throw "Production environment already exists: $environmentPath"
}
if (-not (Test-Path -LiteralPath $lockPath)) {
    throw "Production lock file does not exist: $lockPath"
}

& py "-$PythonVersion" -m venv $environmentPath
if ($LASTEXITCODE -ne 0) {
    throw "Production virtual environment creation failed."
}

& $pythonExe -m pip install "pip==26.1.2"
if ($LASTEXITCODE -ne 0) {
    throw "Pinned pip installation failed."
}

& $pythonExe -m pip install --requirement $lockPath
if ($LASTEXITCODE -ne 0) {
    throw "Production dependency installation failed."
}

& $pythonExe -m pip check
if ($LASTEXITCODE -ne 0) {
    throw "Production dependency consistency check failed."
}

& $pythonExe $verifyScript
if ($LASTEXITCODE -ne 0) {
    throw "Production environment lock verification failed."
}

Write-Host "Production environment created: $environmentPath"
