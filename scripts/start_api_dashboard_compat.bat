@echo off
setlocal
echo Tento kompatibilitni soubor deleguje na produkcni start_api_dashboard.bat.
call "%~dp0..\start_api_dashboard.bat" %*
exit /b %ERRORLEVEL%
