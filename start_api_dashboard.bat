@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%.venv-production\Scripts\python.exe"
set "LOG_RUNNER=%PROJECT_DIR%scripts\run_with_rotating_log.py"
set "ENV_VERIFY=%PROJECT_DIR%scripts\verify_production_environment.py"
set "CADDY_DIR=C:\Program Files\Caddy"
set "CADDY_EXE=%CADDY_DIR%\caddy.exe"
set "CADDY_CONFIG=%CADDY_DIR%\Caddyfile"

if /I "%~1"=="api" goto run_api
if /I "%~1"=="dashboard" goto run_dashboard
if /I "%~1"=="scheduler" goto run_scheduler
if /I "%~1"=="caddy" goto run_caddy

cd /d "%PROJECT_DIR%"

if not exist "%PYTHON_EXE%" (
    echo Nenalezeno: %PYTHON_EXE%
    echo Vytvor produkcni prostredi pres scripts\bootstrap_production_environment.ps1.
    exit /b 1
)

if not exist "%LOG_RUNNER%" (
    echo Nenalezeno: %LOG_RUNNER%
    exit /b 1
)

if not exist "%ENV_VERIFY%" (
    echo Nenalezeno: %ENV_VERIFY%
    exit /b 1
)

"%PYTHON_EXE%" "%ENV_VERIFY%"
if errorlevel 1 (
    echo Produkcni Python prostredi neodpovida requirements-production.lock.txt.
    exit /b 1
)

if not exist "%CADDY_EXE%" (
    echo Nenalezeno: %CADDY_EXE%
    echo Zkontroluj instalaci Caddy v adresari %CADDY_DIR%.
    exit /b 1
)

if not exist "%CADDY_CONFIG%" (
    echo Nenalezeno: %CADDY_CONFIG%
    echo Zkontroluj konfiguraci Caddy v adresari %CADDY_DIR%.
    exit /b 1
)
echo Spoustim API na http://127.0.0.1:8000
start "Monitoring API" cmd /c call "%~f0" api

echo Spoustim scheduler
start "Monitoring Scheduler" cmd /c call "%~f0" scheduler

echo Cekam na dostupnost API...
set "API_READY=0"
for /L %%i in (1,1,45) do (
    "%PYTHON_EXE%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()" >nul 2>nul
    if not errorlevel 1 (
        set "API_READY=1"
        goto api_ready
    )
    <nul set /p="."
    timeout /t 1 /nobreak >nul
)

:api_ready
echo.
if not "%API_READY%"=="1" (
    echo API se nepodarilo overit na http://127.0.0.1:8000/health/live.
    echo Zkontroluj C:\ProgramData\monitorovaci_platforma\logs\api.log.
    exit /b 1
)

echo Spoustim dashboard na http://127.0.0.1:8001
start "Monitoring Dashboard" cmd /c call "%~f0" dashboard

echo Cekam na dostupnost dashboardu...
set "DASHBOARD_READY=0"
for /L %%i in (1,1,45) do (
    "%PYTHON_EXE%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/_stcore/health', timeout=2).read()" >nul 2>nul
    if not errorlevel 1 (
        set "DASHBOARD_READY=1"
        goto dashboard_ready
    )
    <nul set /p="."
    timeout /t 1 /nobreak >nul
)

:dashboard_ready
echo.
if not "%DASHBOARD_READY%"=="1" (
    echo Dashboard se nepodarilo overit na http://127.0.0.1:8001/_stcore/health.
    echo Zkontroluj C:\ProgramData\monitorovaci_platforma\logs\dashboard.log.
    exit /b 1
)

echo Spoustim Caddy pro https://monitoring.armexholding.cz
start "Monitoring Caddy" cmd /c call "%~f0" caddy

echo.
echo API:              http://127.0.0.1:8000
echo Dashboard:        http://127.0.0.1:8001
echo Verejny dashboard: https://monitoring.armexholding.cz
echo Scheduler:        bezi v okne "Monitoring Scheduler"
echo Caddy:            %CADDY_EXE%
echo Caddy config:     %CADDY_CONFIG%
exit /b 0

:run_api
cd /d "%PROJECT_DIR%"
"%PYTHON_EXE%" "%LOG_RUNNER%" --log-name api -- "%PYTHON_EXE%" -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
exit /b %ERRORLEVEL%

:run_dashboard
cd /d "%PROJECT_DIR%"
set "DASHBOARD_API_BASE_URL=http://127.0.0.1:8000"
"%PYTHON_EXE%" "%LOG_RUNNER%" --log-name dashboard -- "%PYTHON_EXE%" -m streamlit run moduly\apps\dashboard\login.py --server.address 127.0.0.1 --server.port 8001 --server.headless true
exit /b %ERRORLEVEL%

:run_scheduler
cd /d "%PROJECT_DIR%"
"%PYTHON_EXE%" main.py
exit /b %ERRORLEVEL%

:run_caddy
if not exist "%CADDY_EXE%" (
    echo Nenalezeno: %CADDY_EXE%
    exit /b 1
)
if not exist "%CADDY_CONFIG%" (
    echo Nenalezeno: %CADDY_CONFIG%
    exit /b 1
)
cd /d "%CADDY_DIR%"
"%CADDY_EXE%" validate --config "%CADDY_CONFIG%" --adapter caddyfile
if errorlevel 1 (
    echo Caddy konfigurace neni platna: %CADDY_CONFIG%
    exit /b 1
)

tasklist /FI "IMAGENAME eq caddy.exe" 2>nul | find /I "caddy.exe" >nul
if not errorlevel 1 (
    echo Caddy uz bezi; nacitam konfiguraci %CADDY_CONFIG%.
    "%CADDY_EXE%" reload --config "%CADDY_CONFIG%" --adapter caddyfile --address 127.0.0.1:2019
    if errorlevel 1 (
        echo Reload Caddy selhal. Zkontroluj admin endpoint 127.0.0.1:2019.
        exit /b 1
    )
    echo Caddy konfigurace byla reloadovana.
    exit /b 0
)

"%PYTHON_EXE%" "%LOG_RUNNER%" --log-name caddy -- "%CADDY_EXE%" run --config "%CADDY_CONFIG%" --adapter caddyfile
exit /b %ERRORLEVEL%
