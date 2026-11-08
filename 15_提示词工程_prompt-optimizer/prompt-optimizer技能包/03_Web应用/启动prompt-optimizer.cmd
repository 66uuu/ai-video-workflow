@echo off
rem 双击启动 prompt-optimizer 本地 Web 应用（端口 8765）并打开浏览器
setlocal
set PROJECT=C:\Users\<USER>\prompt-optimizer
set DIST=%PROJECT%\packages\web\dist
set PORT=8765
set PY=C:\Users\<USER>\.workbuddy\binaries\python\envs\default\python.exe

if not exist "%DIST%\index.html" (
  echo [错误] 未找到 %DIST%\index.html —— Web 应用尚未构建。
  echo 先在 prompt-optimizer 目录执行构建链（pnpm install + core/ui/web build）。
  pause
  exit /b 1
)

echo prompt-optimizer Web: http://127.0.0.1:%PORT%
echo 关闭此窗口即停止服务。
start "" http://127.0.0.1:%PORT%
"%PY%" -m http.server %PORT% --bind 127.0.0.1 --directory "%DIST%"
