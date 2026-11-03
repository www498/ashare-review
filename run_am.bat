@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:/Users/wtr/.workbuddy/binaries/python/versions/3.13.12/python.exe
if not exist logs mkdir logs
"%PY%" run_review.py --session am >> logs\am.log 2>&1
