param(
    [string]$TaskName = "Monitoring_SmartFuelPass_Interactive_Import",
    [string]$UserId = "$env:USERDOMAIN\$env:USERNAME"
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv-production\Scripts\python.exe"
$helperPath = Join-Path $projectRoot "scripts\smartfuelpass_interactive_import.py"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Production Python was not found at the expected project path."
}
if (-not (Test-Path -LiteralPath $helperPath -PathType Leaf)) {
    throw "SmartFuelPass interactive import helper was not found."
}

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument "-m scripts.smartfuelpass_interactive_import" `
    -WorkingDirectory $projectRoot

$principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Interactive `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

$task = New-ScheduledTask `
    -Action $action `
    -Principal $principal `
    -Settings $settings `
    -Description "Manual interactive SmartFuelPass login and database import."

Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $task `
    -Force `
    -ErrorAction Stop | Out-Null

Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop |
    Select-Object TaskName, State, TaskPath
