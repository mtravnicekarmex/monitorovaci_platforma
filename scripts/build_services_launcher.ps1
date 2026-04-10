param(
    [string]$OutputPath = (Join-Path (Join-Path (Split-Path -Parent $PSScriptRoot) "dist") "monitorovaci_platforma_services.exe")
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$sourceLauncher = Join-Path $PSScriptRoot "start_all_services.ps1"
$iexpressExe = Join-Path $env:SystemRoot "System32\iexpress.exe"

if (-not (Test-Path $sourceLauncher)) {
    throw "Launcher script nebyl nalezen: $sourceLauncher"
}

if (-not (Test-Path $iexpressExe)) {
    throw "IExpress nebyl nalezen: $iexpressExe"
}

$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$outputDir = Split-Path -Parent $resolvedOutputPath
$buildRoot = Join-Path $outputDir "_launcher_build"
$packagedLauncher = Join-Path $buildRoot "start_all_services.ps1"
$wrapperCmd = Join-Path $buildRoot "launcher.cmd"
$sedPath = Join-Path $buildRoot "services_launcher.sed"

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

if (Test-Path $buildRoot) {
    Remove-Item -Path $buildRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
Copy-Item -Path $sourceLauncher -Destination $packagedLauncher -Force

$wrapperContent = @"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all_services.ps1" -ProjectRoot "$projectRoot"
"@
Set-Content -Path $wrapperCmd -Value $wrapperContent -Encoding ASCII

$sedContent = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=<None>
AdminQuietInstCmd=%AppLaunched%
UserQuietInstCmd=%AppLaunched%
SourceFiles=SourceFiles

[Strings]
TargetName=$resolvedOutputPath
FriendlyName=Monitoring Platforma Services
AppLaunched=launcher.cmd
FILE0=launcher.cmd
FILE1=start_all_services.ps1

[SourceFiles]
SourceFiles0=$buildRoot

[SourceFiles0]
%FILE0%=
%FILE1%=
"@
Set-Content -Path $sedPath -Value $sedContent -Encoding ASCII

& $iexpressExe /N $sedPath | Out-Null

if (-not (Test-Path $resolvedOutputPath)) {
    throw "IExpress nevytvoril vystupni soubor: $resolvedOutputPath"
}

Remove-Item -Path $buildRoot -Recurse -Force
Write-Output "Vytvoreno: $resolvedOutputPath"
