@echo off
setlocal

set "PROJECT_DIR=%~dp0"

if /I "%~1"=="api" goto run_api
if /I "%~1"=="dashboard" goto run_dashboard

cd /d "%PROJECT_DIR%"

if not exist "%PROJECT_DIR%.venv\Scripts\python.exe" (
    echo Nenalezeno: %PROJECT_DIR%.venv\Scripts\python.exe
    echo Zkontroluj, ze spoustis soubor z korene projektu a ze existuje virtualni prostredi .venv.
    pause
    exit /b 1
)

echo Spoustim API na http://127.0.0.1:8000
start "Monitoring API" cmd /k call "%~f0" api

echo Cekam na dostupnost API...
set "API_READY=0"
for /L %%i in (1,1,45) do (
    "%PROJECT_DIR%.venv\Scripts\python.exe" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()" >nul 2>nul
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
    echo Zkontroluj okno "Monitoring API" a chybovy vystup.
    pause
    exit /b 1
)

echo Spoustim dashboard na http://127.0.0.1:8001
start "Monitoring Dashboard" cmd /k call "%~f0" dashboard

echo.
echo API:       http://127.0.0.1:8000
echo Dashboard: http://127.0.0.1:8001
exit /b 0

:run_api
cd /d "%PROJECT_DIR%"
set "API_TOKEN_SECRET=monitoring-platforma-local-dev-secret"
"%PROJECT_DIR%.venv\Scripts\python.exe" -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000 --reload
exit /b %ERRORLEVEL%

:run_dashboard
cd /d "%PROJECT_DIR%"
set "DASHBOARD_API_BASE_URL=http://127.0.0.1:8000"
"%PROJECT_DIR%.venv\Scripts\python.exe" -m streamlit run moduly\apps\dashboard\login.py --server.port 8001
exit /b %ERRORLEVEL%
