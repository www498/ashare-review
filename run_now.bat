@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:/Users/wtr/.workbuddy/binaries/python/versions/3.13.12/python.exe
set UID=
if exist launch_user.txt set /p UID=<launch_user.txt

echo.
if "%UID%"=="" (
  echo   Run review now ^(single-user mode, about 40 seconds^)...
) else (
  echo   Run review now for account %UID% ^(about 40 seconds^)...
)
echo.

if "%UID%"=="" (
  "%PY%" run_review.py --session pm --forecast
) else (
  "%PY%" run_review.py --session pm --forecast --user "%UID%"
)
if errorlevel 1 goto fail

if "%UID%"=="" (
  start "" "%~dp0reports\index.html"
) else (
  start "" "%~dp0users\%UID%\reports\index.html"
)
exit /b 0

:fail
echo.
echo   [FAILED] check network and try again.
pause
exit /b 1
