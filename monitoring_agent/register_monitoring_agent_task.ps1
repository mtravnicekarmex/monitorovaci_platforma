[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "High")]
param(
    [string]$ProjectRoot = $PSScriptRoot,
    [string]$TaskName = "MonitoringAgentTest"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($TaskName) -or $TaskName.IndexOfAny('\/:*?"<>|'.ToCharArray()) -ge 0) {
    throw "TaskName is invalid."
}

$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$pythonPath = Join-Path $resolvedProjectRoot ".venv\Scripts\python.exe"
$runnerPath = Join-Path $resolvedProjectRoot "run_monitoring_agent.py"
$envPath = Join-Path $resolvedProjectRoot ".env"

foreach ($requiredPath in @($pythonPath, $runnerPath, $envPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "A required monitoring-agent file is unavailable."
    }
}

$action = New-ScheduledTaskAction `
    -Execute $pythonPath `
    -Argument ('"{0}"' -f $runnerPath) `
    -WorkingDirectory $resolvedProjectRoot

$trigger = New-ScheduledTaskTrigger -AtStartup

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Starts the read-only monitoring agent test observer after Windows startup."

if ($PSCmdlet.ShouldProcess($TaskName, "Register or update monitoring-agent startup task")) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -InputObject $task `
        -Force `
        -ErrorAction Stop | Out-Null

    Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop |
        Select-Object TaskName, State, TaskPath
}
