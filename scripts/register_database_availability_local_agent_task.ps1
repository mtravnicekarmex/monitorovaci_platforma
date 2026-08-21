param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "MonitoringDatabaseAvailabilityLocalAgent",
    [int]$IntervalMinutes = 5,
    [string]$PythonExe = "",
    [string]$StateFile = "",
    [string]$DbFile = ""
)

$ErrorActionPreference = "Stop"

if ($IntervalMinutes -lt 1) {
    throw "IntervalMinutes must be at least 1."
}

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$runner = Join-Path $resolvedProjectRoot "scripts\run_database_availability_local_agent.py"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Database availability local-agent runner was not found: $runner"
}

if (-not $PythonExe) {
    $PythonExe = Join-Path $resolvedProjectRoot ".venv\Scripts\python.exe"
}
$resolvedPython = (Resolve-Path $PythonExe).Path

$taskArguments = @(
    "`"$runner`""
)

if ($StateFile) {
    $taskArguments += @("--state-file", "`"$StateFile`"")
}

if ($DbFile) {
    $taskArguments += @("--db-file", "`"$DbFile`"")
}

$action = New-ScheduledTaskAction `
    -Execute $resolvedPython `
    -Argument ($taskArguments -join " ") `
    -WorkingDirectory $resolvedProjectRoot

$startAt = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $startAt `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Runs the local read-only database-availability monitoring agent and writes sanitized agent-owned state." `
    -Force | Out-Null

Write-Output (
    "Registered scheduled task '{0}' every {1} minute(s)." -f
    $TaskName,
    $IntervalMinutes
)
