@echo off
chcp 65001 >nul
title 本地工具接入 · 快速出视频
cd /d "%~dp0bridge"

echo ============================================================
echo   快速出视频（Wan2.2 TI2V-5B，72 帧约 5 分钟）
echo ============================================================
echo.
echo   提示词写四段：动作 + 声景 + 配乐 + 镜头
echo   禁止写画风、长相、服装、姓名（会和首帧图打架 → 换脸）
echo   一镜只写一个能在几秒内做完的动作，结尾要有"停住"
echo.
echo   例：夜，一名女子缓慢抬头，停住。雨声持续。无配乐。近景，50mm，浅景深。
echo.

set /p IMG=首帧图片路径: 
if "%IMG%"=="" (
  echo [错误] 首帧是必需的。
  pause
  exit /b 1
)
set /p PROMPT=提示词: 
if "%PROMPT%"=="" set "PROMPT=夜，画面中的人极缓地抬起头，然后停住。雨声持续。无配乐。近景，50mm，浅景深。"
set /p FR=帧数（24fps，回车=72即3秒）: 
if "%FR%"=="" set "FR=72"

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

echo.
echo 开始。72 帧约 286 秒，121 帧约 572 秒，请耐心等。
echo.
%PY% nr_bridge.py i2v --image "%IMG%" --prompt "%PROMPT%" --frames %FR% --out "..\_产出"

echo.
echo 产物在 ..\_产出\
pause
