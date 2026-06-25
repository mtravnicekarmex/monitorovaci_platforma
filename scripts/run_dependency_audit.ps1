param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ReportDir = "",
    [string]$RequirementsPath = "",
    [string]$SecurityVenvPath = "",
    [string]$ProductionVenvPath = ""
)

$ErrorActionPreference = "Stop"

function Get-DefaultProgramDataRoot {
    param([string]$ResolvedProjectRoot)

    if ($env:PROGRAMDATA) {
        return (Join-Path $env:PROGRAMDATA "monitorovaci_platforma")
    }
    return (Join-Path $ResolvedProjectRoot ".codex\local_programdata")
}

function Invoke-AuditCommand {
    param(
        [string]$CommandPath,
        [string[]]$CommandArguments
    )

    & $CommandPath @CommandArguments
    return $LASTEXITCODE
}

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
if (-not $ReportDir) {
    $ReportDir = Join-Path (Get-DefaultProgramDataRoot $resolvedProjectRoot) "logs\security"
}
if (-not $RequirementsPath) {
    $RequirementsPath = Join-Path $resolvedProjectRoot "requirements-production.lock.txt"
}
if (-not $SecurityVenvPath) {
    $SecurityVenvPath = Join-Path $resolvedProjectRoot ".venv-security"
}
if (-not $ProductionVenvPath) {
    $ProductionVenvPath = Join-Path $resolvedProjectRoot ".venv-production"
}

$auditPython = Join-Path $SecurityVenvPath "Scripts\python.exe"
$productionPython = Join-Path $ProductionVenvPath "Scripts\python.exe"
$verifyScript = Join-Path $resolvedProjectRoot "scripts\verify_production_environment.py"

foreach ($requiredPath in @($auditPython, $productionPython, $RequirementsPath, $verifyScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required dependency audit file was not found: $requiredPath"
    }
}

& $productionPython $verifyScript
if ($LASTEXITCODE -ne 0) {
    throw "Production environment lock verification failed before dependency audit."
}

$sitePackages = (& $productionPython -c "import sysconfig; print(sysconfig.get_paths()['purelib'])").Trim()
if ($LASTEXITCODE -ne 0 -or -not $sitePackages) {
    throw "Could not determine production site-packages path."
}

New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$requirementsReport = Join-Path $ReportDir ("dependency_audit_requirements_{0}.json" -f $timestamp)
$environmentReport = Join-Path $ReportDir ("dependency_audit_environment_{0}.json" -f $timestamp)
$summaryReport = Join-Path $ReportDir "dependency_audit_latest.json"

$requirementsExit = Invoke-AuditCommand `
    -CommandPath $auditPython `
    -CommandArguments @(
        "-m", "pip_audit",
        "--requirement", $RequirementsPath,
        "--no-deps",
        "--format", "json",
        "--output", $requirementsReport,
        "--progress-spinner", "off",
        "--desc", "off",
        "--aliases", "on"
    )

$environmentExit = Invoke-AuditCommand `
    -CommandPath $auditPython `
    -CommandArguments @(
        "-m", "pip_audit",
        "--path", $sitePackages,
        "--format", "json",
        "--output", $environmentReport,
        "--progress-spinner", "off",
        "--desc", "off",
        "--aliases", "on"
    )

$status = "ok"
if ($requirementsExit -ne 0 -or $environmentExit -ne 0) {
    $status = "vulnerabilities_or_error"
}

$summary = [ordered]@{
    status = $status
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    project_root = $resolvedProjectRoot
    requirements_path = (Resolve-Path $RequirementsPath).Path
    production_site_packages = $sitePackages
    requirements_exit_code = $requirementsExit
    environment_exit_code = $environmentExit
    requirements_report = $requirementsReport
    environment_report = $environmentReport
}

$summary | ConvertTo-Json -Depth 4 | Set-Content -Path $summaryReport -Encoding UTF8

Write-Output ("Dependency audit status: {0}" -f $status)
Write-Output ("Requirements report: {0}" -f $requirementsReport)
Write-Output ("Environment report: {0}" -f $environmentReport)
Write-Output ("Latest summary: {0}" -f $summaryReport)

if ($environmentExit -ne 0) {
    exit $environmentExit
}
exit $requirementsExit
