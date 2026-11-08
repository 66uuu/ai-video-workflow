@echo off
chcp 65001 >nul
title 出片到 D 盘成果区（收片 → 拼片 → 打包）
set "HERE=%~dp0"
cd /d "%HERE%"
set "PY=ComfyUI\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "PROJECT_ROOT=%NR_PROJECT_ROOT%"
if not defined PROJECT_ROOT set "PROJECT_ROOT=%HERE%.."

echo ============================================================
echo   出片到桌面
echo   项目：%PROJECT_ROOT%
echo   1) 收片+质检  2) 拼片(调色+溶解)  3) 打包到 D 盘成果区
echo ============================================================
echo.

echo [1/3] 收片与质检...
"%PY%" batch_local.py --collect --project-root "%PROJECT_ROOT%"
if errorlevel 1 goto :fail

echo.
echo [2/3] 拼片...
"%PY%" assemble_ep04.py --grade --xfade 0.20 --project-root "%PROJECT_ROOT%"
if errorlevel 1 goto :fail

:done
echo.
echo 完成。正片和交付包都在 你的桌面\AI产物 或项目成果区。
pause
exit /b 0

:fail
echo.
echo 拼片失败（多半是缺镜头，脚本会拒绝出正片）。看上面缺哪几镜。
pause
exit /b 1
