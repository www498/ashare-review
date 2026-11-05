@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=C:/Users/wtr/.workbuddy/binaries/python/versions/3.13.12/python.exe
title 推送到 Gitee
echo.
echo   ==================================================
echo    把代码推送到 Gitee（给评委审查用）
echo   ==================================================
echo.
echo   开始前确认：
echo     1. 已在 gitee.com 建好空仓库
echo        注意：不要勾选「使用 Readme 文件初始化这个仓库」
echo     2. 已生成私人令牌：设置 - 私人令牌 - 勾选 projects
echo     3. 仓库地址形如：
echo        https://gitee.com/你的名字/ashare-review.git
echo.
set /p REPO=1) 仓库地址:
set /p GUSER=2) Gitee 用户名:
set /p TOKEN=3) 私人令牌:
echo.
echo   正在推送，请稍候（首次约 1-2 分钟）...
echo.
"%PY%" tools\cn_push.py "%REPO%" "%GUSER%" "%TOKEN%"
echo.
echo   推送结束。请到 gitee.com 打开仓库，确认文件都在。
pause
