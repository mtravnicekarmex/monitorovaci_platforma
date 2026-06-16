@echo off
echo Tento kompatibilitni soubor deleguje na produkcni start_api_dashboard.bat.
call "%~dp0start_api_dashboard.bat" %*
exit /b %ERRORLEVEL%
