@echo off
chcp 65001 >nul
title 全链路出片（收片 → 拼片 → 字卡 → 挂音轨字幕 → 混音 → 剪映草稿）
set "HERE=%~dp0"
cd /d "%HERE%"
set "EP=%~1"
if "%EP%"=="" set "EP=EP04"

set "PY=ComfyUI\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo ============================================================
echo   全链路出片  %EP%
echo   1) 收片+质检  2) 拼片(调色+溶解)  3) 字卡  4) 配音+字幕  5) 音效混音  6) 剪映草稿(可选)
echo ============================================================
echo.

echo [1/5] 收片与质检...
"%PY%" batch_local.py --collect
if errorlevel 1 echo   ! 有镜头质检未过，继续往下走，回头再补

echo.
echo [2/5] 拼片（统一调色 + 镜头间溶解 0.2s）...
"%PY%" assemble_ep04.py --grade --xfade 0.20 --no-desktop
if errorlevel 1 goto :fail

set "PIC="
for %%f in (..\*%EP%_正片_*.mp4) do set "PIC=%%f"
if "%PIC%"=="" (
  echo   ! 找不到正片，后面跳过
  goto :done
)

echo.
echo [3/5] 字卡...
set "CARDS=..\06_分镜与时间轴\cards_%EP%.json"
if exist "%CARDS%" (
  "%PY%" card_gen.py --video "%PIC%" --cards "%CARDS%" --out "..\_产出\%EP%_字卡.mp4"
  if not errorlevel 1 set "PIC=..\_产出\%EP%_字卡.mp4"
) else (
  echo   跳过：没有 %CARDS%（要片头标题可手工跑 card_gen.py --auto --title "..."）
)

echo.
echo [4/5] 挂配音与字幕...
set "VOICE=..\_产出\配音_%EP%\voice_track.wav"
set "SRT=..\_产出\配音_%EP%\voice_track.srt"
if not exist "%VOICE%" (
  echo   跳过：没有 %VOICE%
  goto :mix
)
"%PY%" mux_audio.py --video "%PIC%" --audio "%VOICE%" --srt "%SRT%" --burn --out "..\_产出\%EP%_有声版_字幕烧录.mp4"

:mix
echo.
echo [5/5] 音效与响度...
set "TL=..\06_分镜与时间轴\%EP%_timeline_v2.json"
if not exist "%TL%" goto :done
if not exist "%VOICE%" goto :done
if not exist "%PIC%" goto :done
"%PY%" audio_mix.py --video "%PIC%" --voice "%VOICE%" --auto --timeline "%TL%" --out "..\_产出\%EP%_混音版.mp4"
if errorlevel 1 goto :fail

echo.
echo [6/6] 生成剪映草稿（可选，用系统 Python）...
set "TL6=..\06_分镜与时间轴\%EP%_timeline_v2.json"
set "VDIR=..\video_i2v"
if not exist "%TL6%" (
  echo   跳过：没有 %TL6%
  goto :done
)
python gen_jianying_draft.py --timeline "%TL6%" --video-dir "%VDIR%" --name "%EP%_自动组装" --allow-replace
if errorlevel 1 echo   ! 剪映草稿生成失败（不影响成片；缺依赖先执行 python -m pip install pyJianYingDraft）

:done
echo.
echo 完成。产出在 ..\_产出\
pause
exit /b 0

:fail
echo.
echo 失败，后面的步骤跳过。
pause
exit /b 1
