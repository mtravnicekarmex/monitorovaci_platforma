param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "MonitoringDependencyAudit",
    [string]$DailyAt = "03:40",
    [string]$ReportDir = ""
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$runner = Join-Path $resolvedProjectRoot "scripts\run_dependency_audit.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Dependency audit runner was not found: $runner"
}

$time = [DateTime]::ParseExact($DailyAt, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
$taskArguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$runner`"",
    "-ProjectRoot", "`"$resolvedProjectRoot`""
)

if ($ReportDir) {
    $taskArguments += @("-ReportDir", "`"$ReportDir`"")
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ($taskArguments -join " ")
$trigger = New-ScheduledTaskTrigger -Daily -At $time
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 45)
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
    -Description "Runs the monitorovaci_platforma dependency vulnerability audit and writes ProgramData reports." `
    -Force | Out-Null

Write-Output ("Registered scheduled task '{0}' for {1}." -f $TaskName, $DailyAt)
