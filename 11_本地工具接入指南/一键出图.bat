@echo off
chcp 65001 >nul
title 本地工具接入 · 快速出图
cd /d "%~dp0bridge"

echo ============================================================
echo   快速出图（本机 SD1.5，约 8 秒一张）
echo ============================================================
echo.
echo   提示词用英文。参考图可以不填（不填就是纯文生图）。
echo   挂参考图能保住人物的脸，权重建议：
echo     换场景 0.5  /  同场景换机位 0.75  /  只改表情 0.9
echo.

set /p PROMPT=提示词（留空则用示例）: 
if "%PROMPT%"=="" set "PROMPT=1girl, solo, portrait, soft natural daylight, bright and airy, 85mm, shallow depth of field, looking at viewer"
echo.
set /p REF=参考图路径（直接回车跳过）: 
set /p W=参考图权重（回车=0.5）: 
if "%W%"=="" set "W=0.5"

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
if "%REF%"=="" (
  %PY% nr_bridge.py t2i --prompt "%PROMPT%" --out "..\_产出"
) else (
  %PY% nr_bridge.py t2i --prompt "%PROMPT%" --ref "%REF%" --ref-weight %W% --out "..\_产出"
)

echo.
echo 产物在 ..\_产出\
pause
