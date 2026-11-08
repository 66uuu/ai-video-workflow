@echo off
chcp 65001 >nul
title 本地工具接入 · 环境体检
cd /d "%~dp0bridge"

echo ============================================================
echo   环境体检
echo   检查：ComfyUI目录 / 服务 / 显存 / 模型 / 节点 / ffmpeg
echo ============================================================
echo.

set "PY="
if not defined PY if exist "ComfyUI\venv\Scripts\python.exe" set "PY=ComfyUI\venv\Scripts\python.exe"
if not defined PY if exist "F:\ComfyUI\venv\Scripts\python.exe" set "PY=F:\ComfyUI\venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [错误] 没找到 python。
  echo        请确认 ComfyUI 或系统 Python 已安装。
  echo        ComfyUI\venv\Scripts\python.exe selfcheck.py
  pause
  exit /b 1
)

%PY% selfcheck.py %*

echo.
echo ------------------------------------------------------------
echo 想连出图出视频一起验证，跑这个（会占队列，约 1-2 分钟）：
echo   双击 一键验证_出图出视频.bat
echo ------------------------------------------------------------
pause
