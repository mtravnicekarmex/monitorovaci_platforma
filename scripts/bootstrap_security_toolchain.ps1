param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PythonVersion = "3.14"
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$environmentPath = Join-Path $resolvedProjectRoot ".venv-security"
$pythonExe = Join-Path $environmentPath "Scripts\python.exe"
$lockPath = Join-Path $resolvedProjectRoot "requirements-security.lock.txt"

if (Test-Path -LiteralPath $environmentPath) {
    throw "Security tooling environment already exists: $environmentPath"
}
if (-not (Test-Path -LiteralPath $lockPath)) {
    throw "Security tooling lock file does not exist: $lockPath"
}

& py "-$PythonVersion" -m venv $environmentPath
if ($LASTEXITCODE -ne 0) {
    throw "Security tooling virtual environment creation failed."
}

& $pythonExe -m pip install "pip==26.1.2"
if ($LASTEXITCODE -ne 0) {
    throw "Pinned pip installation failed."
}

& $pythonExe -m pip install --requirement $lockPath
if ($LASTEXITCODE -ne 0) {
    throw "Security tooling dependency installation failed."
}

& $pythonExe -m pip check
if ($LASTEXITCODE -ne 0) {
    throw "Security tooling dependency consistency check failed."
}

& $pythonExe -m pip_audit --version
if ($LASTEXITCODE -ne 0) {
    throw "pip-audit verification failed."
}

Write-Host "Security tooling environment created: $environmentPath"
