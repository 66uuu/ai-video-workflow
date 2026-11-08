@echo off
chcp 65001 >nul
title 生成 EP04（提交 + 等 + 收片 + 质检）
set "HERE=%~dp0"
cd /d "%HERE%"
set "PY=ComfyUI\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PROJECT_ROOT=%NR_PROJECT_ROOT%"
if not defined PROJECT_ROOT set "PROJECT_ROOT=%HERE%.."

echo ============================================================
echo   EP04 逐镜生成
echo   先全部入队，再依次收片（比逐条提交快 3 倍以上）
echo ============================================================
echo.
"%PY%" batch_local.py --project-root "%PROJECT_ROOT%" --episode EP04
if errorlevel 1 goto :fail

echo.
echo 完成。片子在项目的 视频\ 下，成果在 你的桌面\AI产物。
pause
exit /b 0

:fail
echo.
echo 有镜头失败，看上面的原因；补拍用 batch_local.py --only S13 --force
pause
exit /b 1
