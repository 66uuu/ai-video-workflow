@echo off
chcp 65001 >nul
title 本地工具接入 · 端到端验证
cd /d "%~dp0bridge"

echo ============================================================
echo   端到端验证
echo   1) 查节点   2) 真出一张图   3) 用那张图出一段 16 帧视频
echo   全程走本机显卡，不消耗任何外部额度
echo ============================================================
echo.
echo   注意：会占用队列。如果 ComfyUI 正在跑别的任务，
echo         本验证会插到队首，只延后当前那一镜。
echo.
pause

set "PY="
if exist "源机器E盘ComfyUI\venv\Scripts\python.exe" set "PY=源机器E盘ComfyUI\venv\Scripts\python.exe"
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
  pause
  exit /b 1
)

%PY% selfcheck.py --run

echo.
echo 产物在 ..\_产出\selfcheck\
pause
