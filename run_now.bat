@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:/Users/wtr/.workbuddy/binaries/python/versions/3.13.12/python.exe
echo.
echo   Run review now (about 40 seconds)...
echo.
"%PY%" run_review.py --session pm --forecast
if errorlevel 1 goto fail
start "" "%~dp0reports\index.html"
exit /b 0
:fail
echo.
echo   [FAILED] check network and try again.
pause
exit /b 1
