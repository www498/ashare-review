@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:/Users/wtr/.workbuddy/binaries/python/versions/3.13.12/python.exe
title A-Share Review Workbench
echo.
echo   Starting workbench at http://127.0.0.1:8765
echo   Browser opens automatically. Use the gear button for
echo   import / regenerate / switch reports. Ctrl+C to stop.
echo.
"%PY%" -m ashare.importer
pause
