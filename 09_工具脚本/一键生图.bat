@echo off
chcp 65001 >nul
title 批量生图（任务单）
set "HERE=%~dp0"
cd /d "%HERE%"
set "PY=ComfyUI\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo ============================================================
echo   批量生图  IMAGES.json
echo ============================================================
echo.
"%PY%" gen_image.py --jobs "IMAGES.json" --desktop
if errorlevel 1 goto :fail

echo.
echo 完成。出图在 ..\_本地生图\ 和桌面。
pause
exit /b 0

:fail
echo.
echo 生图失败，先看上面的报错。
pause
exit /b 1
