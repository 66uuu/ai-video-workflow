@echo off
chcp 65001 >nul
cd /d ComfyUI

:: ============================================================
::  ComfyUI 启动（优化版）
::
::  ★ 先说结论：本机慢的不是采样，是"每跑一条都重新加载模型"。
::     实测（RTX 4060 8G / 384x576 / 12步 / euler）：
::        13 帧   87.7 秒   ← 其中约 71 秒是加载，采样只占 16 秒
::        49 帧  133.4 秒   ← 每帧只要 1.27 秒
::
::     真正的解法是「一次性入队」，已经内置在 batch_local.py 里，
::     24 镜从约 35 分钟降到约 11 分钟。跟本 bat 无关。
::
::  ★ 这个 bat 只做三件确实有用的小事：
::     1) --preview-method none  关掉采样预览，省 3-8% 时间
::     2) 清掉 8188 端口的残留进程，避免 "address in use"
::     3) 临时目录/缓存钉在 D 盘，不碰 C 盘
::
::  ★ 想要更快，比改参数有效得多的两件事：
::     · 跑之前关掉 AutoCAD、Edge 浏览器（它们常占 3-4G 显存，
::       直接导致模型在显存里留不住，每次都要重装）
::     · 一次跑多条，不要一条一条点
::
::  注意：--cache-ram 本来就是默认模式，显式写上也不会让模型常驻，
::        别再花时间试这个开关了（已实测无效）。
:: ============================================================

set TEMP=ComfyUI\tmp
set TMP=ComfyUI\tmp
set TMPDIR=ComfyUI\tmp
set PIP_CACHE_DIR=<D盘>\pip_cache
set HF_ENDPOINT=https://hf-mirror.com
set HF_HOME=ComfyUI\hf_cache
set HF_HUB_CACHE=ComfyUI\hf_cache\hub

mkdir "%TEMP%" 2>nul

:: 清理占用 8188 的残留进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8188 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1

echo.
echo 正在启动 ComfyUI...
echo   关掉 AutoCAD / 浏览器 能明显提速（释放 3-4G 显存）
echo.

ComfyUI\venv\Scripts\python.exe main.py ^
  --listen 127.0.0.1 --port 8188 ^
  --preview-method none

pause
