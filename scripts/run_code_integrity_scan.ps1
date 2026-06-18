param(
    [ValidateSet("Scan", "Baseline")]
    [string]$Mode = "Scan",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ManifestPath = "",
    [string]$ReportDir = "",
    [switch]$AllowDirtyBaseline
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$pythonExe = Join-Path $resolvedProjectRoot ".venv-production\Scripts\python.exe"
$scanner = Join-Path $resolvedProjectRoot "scripts\code_integrity_scan.py"

foreach ($requiredPath in @($pythonExe, $scanner)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required code integrity scan file was not found: $requiredPath"
    }
}

$arguments = @(
    $scanner,
    $Mode.ToLowerInvariant(),
    "--project-root",
    $resolvedProjectRoot
)

if ($ManifestPath) {
    $arguments += @("--manifest", $ManifestPath)
}

if ($ReportDir) {
    $arguments += @("--report-dir", $ReportDir)
}

if ($Mode -eq "Baseline" -and $AllowDirtyBaseline) {
    $arguments += "--allow-dirty"
}

& $pythonExe @arguments
exit $LASTEXITCODE
