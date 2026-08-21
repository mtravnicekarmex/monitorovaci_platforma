param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "MonitoringLocalAgents",
    [int]$IntervalMinutes = 5,
    [string]$PythonExe = "",
    [string]$DatabaseAvailabilityStateFile = "",
    [string]$DatabaseAvailabilityDbFile = "",
    [string]$SchedulerMetricsStateFile = "",
    [string]$SchedulerMetricsFile = ""
)

$ErrorActionPreference = "Stop"

if ($IntervalMinutes -lt 1) {
    throw "IntervalMinutes must be at least 1."
}

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$runner = Join-Path $resolvedProjectRoot "scripts\run_local_monitoring_agents.py"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Local monitoring agents runner was not found: $runner"
}

if (-not $PythonExe) {
    $PythonExe = Join-Path $resolvedProjectRoot ".venv\Scripts\python.exe"
}
$resolvedPython = (Resolve-Path $PythonExe).Path

$taskArguments = @(
    "`"$runner`""
)

if ($DatabaseAvailabilityStateFile) {
    $taskArguments += @(
        "--database-availability-state-file",
        "`"$DatabaseAvailabilityStateFile`""
    )
}

if ($DatabaseAvailabilityDbFile) {
    $taskArguments += @(
        "--database-availability-db-file",
        "`"$DatabaseAvailabilityDbFile`""
    )
}

if ($SchedulerMetricsStateFile) {
    $taskArguments += @(
        "--scheduler-metrics-state-file",
        "`"$SchedulerMetricsStateFile`""
    )
}

if ($SchedulerMetricsFile) {
    $taskArguments += @("--scheduler-metrics-file", "`"$SchedulerMetricsFile`"")
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
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3)

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
    -Description "Runs approved local monitoring agents and writes sanitized agent-owned state." `
    -Force | Out-Null

Write-Output (
    "Registered scheduled task '{0}' every {1} minute(s)." -f
    $TaskName,
    $IntervalMinutes
)
