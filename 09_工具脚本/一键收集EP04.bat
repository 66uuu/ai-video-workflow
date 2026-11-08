@echo off
chcp 65001 >nul
title 收集 EP04（只收片 + 质检）
set "HERE=%~dp0"
cd /d "%HERE%"
set "PY=ComfyUI\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo ============================================================
echo   收集 EP04（队列已经压过了，这里只收片）
echo ============================================================
echo.
"%PY%" batch_local.py --collect
if errorlevel 1 goto :fail

echo.
echo 完成。
pause
exit /b 0

:fail
echo.
echo 有镜头未完成或质检未过，看上面清单。
pause
exit /b 1
