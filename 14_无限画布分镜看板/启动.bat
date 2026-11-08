@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "frontend\dist\index.html" (
    echo [首次运行] 未找到前端构建产物，开始构建（首次需联网下载依赖）...
    cd frontend
    call npm install --no-audit --no-fund
    if errorlevel 1 (
        echo [错误] npm install 失败，请确认已安装 Node.js 且网络可用。
        pause
        exit /b 1
    )
    call npm run build
    cd ..
)

echo 正在启动分镜无限画布看板...
start "shotboard-server" cmd /c python server.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8080

echo.
echo 浏览器已打开 http://127.0.0.1:8080
echo 如需停止服务，请关闭标题为 shotboard-server 的命令窗口。
echo.
pause