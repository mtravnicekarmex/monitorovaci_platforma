param(
    [string]$CaddyDirectory = "C:\Program Files\Caddy"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceConfig = Join-Path $projectRoot "Caddyfile"
$launcher = Join-Path $projectRoot "start_api_dashboard.bat"
$caddyExe = Join-Path $CaddyDirectory "caddy.exe"
$runtimeConfig = Join-Path $CaddyDirectory "Caddyfile"

$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run from an elevated administrator PowerShell session."
}

foreach ($requiredPath in @($sourceConfig, $launcher, $caddyExe, $runtimeConfig)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required file does not exist: $requiredPath"
    }
}

& $caddyExe validate `
    --config $sourceConfig `
    --adapter caddyfile
if ($LASTEXITCODE -ne 0) {
    throw "Project Caddy configuration validation failed."
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $CaddyDirectory "Caddyfile.pre-deploy-$timestamp"
Copy-Item -LiteralPath $runtimeConfig -Destination $backupPath

try {
    Copy-Item -LiteralPath $sourceConfig -Destination $runtimeConfig -Force
    & $env:ComSpec /d /c "call `"$launcher`" caddy"
    if ($LASTEXITCODE -ne 0) {
        throw "Caddy reload failed with exit code $LASTEXITCODE."
    }
}
catch {
    Copy-Item -LiteralPath $backupPath -Destination $runtimeConfig -Force
    & $env:ComSpec /d /c "call `"$launcher`" caddy"
    throw
}

Write-Host "Caddy runtime configuration deployed."
Write-Host "Backup: $backupPath"
