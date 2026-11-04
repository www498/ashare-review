@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:/Users/wtr/.workbuddy/binaries/python/versions/3.13.12/python.exe
title Ashare Review Scheduler
echo.
echo   ==========================================
echo    Ashare Review - auto scheduler
echo    Weekdays 11:35 midday / 15:05 close
echo    KEEP THIS WINDOW OPEN
echo   ==========================================
echo.
"%PY%" scheduler.py
echo.
echo   Scheduler stopped.
pause
