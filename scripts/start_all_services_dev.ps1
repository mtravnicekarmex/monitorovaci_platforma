param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$resolvedProjectRoot = (Resolve-Path $ProjectRoot).Path
$pythonExe = Join-Path $resolvedProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Development environment was not found at '$pythonExe'."
}

$services = @(
    @{
        Name = "Monitoring API Dev"
        Arguments = @(
            "-m", "uvicorn", "services.api.main:app",
            "--host", "127.0.0.1",
            "--port", "8000",
            "--reload",
            "--proxy-headers",
            "--forwarded-allow-ips", "127.0.0.1"
        )
    },
    @{
        Name = "Monitoring Dashboard Dev"
        Arguments = @(
            "-m", "streamlit", "run", "moduly\apps\dashboard\login.py",
            "--server.address", "127.0.0.1",
            "--server.port", "8001",
            "--server.headless", "true"
        )
    },
    @{
        Name = "Monitoring Scheduler Dev"
        Arguments = @("main.py")
    }
)

foreach ($service in $services) {
    if ($DryRun) {
        Write-Output ("[{0}] {1} {2}" -f $service.Name, $pythonExe, ($service.Arguments -join " "))
        continue
    }

    $environment = if ($service.Name -eq "Monitoring Dashboard Dev") {
        @{ DASHBOARD_API_BASE_URL = "http://127.0.0.1:8000" }
    } else {
        @{}
    }
    $previousEnvironment = @{}
    try {
        foreach ($item in $environment.GetEnumerator()) {
            $existing = Get-Item -Path "Env:$($item.Key)" -ErrorAction SilentlyContinue
            $previousEnvironment[$item.Key] = if ($null -eq $existing) {
                $null
            } else {
                $existing.Value
            }
            Set-Item -Path "Env:$($item.Key)" -Value $item.Value
        }

        Start-Process `
            -FilePath $pythonExe `
            -ArgumentList $service.Arguments `
            -WorkingDirectory $resolvedProjectRoot `
            -PassThru | ForEach-Object {
                Write-Output ("Started: {0} (PID={1})" -f $service.Name, $_.Id)
            }
    } finally {
        foreach ($item in $previousEnvironment.GetEnumerator()) {
            if ($null -eq $item.Value) {
                Remove-Item -Path "Env:$($item.Key)" -ErrorAction SilentlyContinue
            } else {
                Set-Item -Path "Env:$($item.Key)" -Value $item.Value
            }
        }
    }
    Start-Sleep -Milliseconds 300
}
