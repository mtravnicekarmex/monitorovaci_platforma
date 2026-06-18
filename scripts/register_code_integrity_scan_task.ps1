param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "MonitoringCodeIntegrityScan",
    [string]$DailyAt = "03:20",
    [string]$ManifestPath = "",
    [string]$ReportDir = ""
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$runner = Join-Path $resolvedProjectRoot "scripts\run_code_integrity_scan.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Code integrity scan runner was not found: $runner"
}

$time = [DateTime]::ParseExact($DailyAt, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
$taskArguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$runner`"",
    "-Mode", "Scan",
    "-ProjectRoot", "`"$resolvedProjectRoot`""
)

if ($ManifestPath) {
    $taskArguments += @("-ManifestPath", "`"$ManifestPath`"")
}

if ($ReportDir) {
    $taskArguments += @("-ReportDir", "`"$ReportDir`"")
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ($taskArguments -join " ")
$trigger = New-ScheduledTaskTrigger -Daily -At $time.TimeOfDay
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType InteractiveToken `
    -RunLevel LeastPrivilege

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Runs the monitorovaci_platforma code integrity scan against the approved ProgramData manifest." `
    -Force | Out-Null

Write-Output ("Registered scheduled task '{0}' for {1}." -f $TaskName, $DailyAt)
