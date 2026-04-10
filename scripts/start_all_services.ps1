param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$pythonExe = Join-Path $resolvedProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment nebyl nalezen v '$pythonExe'."
}

function New-ServiceCommand {
    param(
        [string]$ProjectRootPath,
        [string]$PythonPath,
        [string]$WindowTitle,
        [string]$EnvironmentAssignment,
        [string]$CommandLine
    )

    $segments = @(
        "title $WindowTitle",
        "cd /d `"$ProjectRootPath`""
    )

    if ($EnvironmentAssignment) {
        $segments += "set `"$EnvironmentAssignment`""
    }

    $segments += "`"$PythonPath`" $CommandLine"
    return ($segments -join " && ")
}


$services = @(
    @{
        Name = "Monitoring API"
        Command = New-ServiceCommand `
            -ProjectRootPath $resolvedProjectRoot `
            -PythonPath $pythonExe `
            -WindowTitle "Monitoring API" `
            -EnvironmentAssignment "API_TOKEN_SECRET=monitoring-platforma-local-dev-secret" `
            -CommandLine '-m uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --reload'
    },
    @{
        Name = "Monitoring Dashboard"
        Command = New-ServiceCommand `
            -ProjectRootPath $resolvedProjectRoot `
            -PythonPath $pythonExe `
            -WindowTitle "Monitoring Dashboard" `
            -EnvironmentAssignment "DASHBOARD_API_BASE_URL=http://127.0.0.1:8000" `
            -CommandLine '-m streamlit run moduly\apps\dashboard\login.py --server.port 8001'
    },
    @{
        Name = "Monitoring Scheduler"
        Command = New-ServiceCommand `
            -ProjectRootPath $resolvedProjectRoot `
            -PythonPath $pythonExe `
            -WindowTitle "Monitoring Scheduler" `
            -EnvironmentAssignment '' `
            -CommandLine 'main.py'
    }
)

foreach ($service in $services) {
    if ($DryRun) {
        Write-Output ("[{0}] cmd.exe /k {1}" -f $service.Name, $service.Command)
        continue
    }

    $process = Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList "/k", $service.Command `
        -WorkingDirectory $resolvedProjectRoot `
        -PassThru

    Write-Output ("Spusteno: {0} (PID={1})" -f $service.Name, $process.Id)
    Start-Sleep -Milliseconds 300
}
