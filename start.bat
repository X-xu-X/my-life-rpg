@echo off
setlocal
title Game of Life - Launcher
cd /d "%~dp0"

REM ============================================================
REM  用法：
REM    双击 start.bat        -> 仅本机访问 http://127.0.0.1:5173
REM    双击 start-phone.bat  -> 局域网模式，手机可访问（同一 WiFi）
REM    （等价于 start.bat phone）
REM ============================================================
set "PHONE_MODE=0"
if /i "%~1"=="phone" set "PHONE_MODE=1"

echo ============================================
echo   游戏人生 Game of Life - 一键启动
if "%PHONE_MODE%"=="1" echo   模式：局域网（手机可访问）
echo ============================================
echo.

REM ========== 0. 清理旧进程，释放端口 ==========
echo [0/5] 清理占用 8000/5173 的旧进程（如有）...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /f /pid %%p >nul 2>nul
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do taskkill /f /pid %%p >nul 2>nul

REM ========== 1. 检查 .env ==========
if not exist ".env" (
    echo [准备] 未找到 .env，正在从模板复制...
    copy ".env.example" ".env" >nul
    echo [重要] 已生成 .env，请先填入 DeepSeek API Key 后重新运行！
    start notepad ".env"
    pause
    exit /b 1
)

REM ========== 2. 后端 Python 环境 ==========
echo [1/5] 检查后端 Python 环境...
set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo       未找到项目虚拟环境，正在创建并安装依赖（首次约 1-2 分钟）...
    python -m venv ".venv"
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败，请确认已安装 Python 3.10+ 并加入 PATH
        pause
        exit /b 1
    )
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 后端依赖安装失败，请检查网络后重试
        pause
        exit /b 1
    )
)

"%PYTHON%" -c "import fastapi, uvicorn, sqlalchemy, openai, dotenv" >nul 2>nul
if errorlevel 1 (
    echo       检测到后端依赖缺失，正在安装...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 后端依赖安装失败，请检查网络后重试
        pause
        exit /b 1
    )
)

REM ========== 3. 前端依赖 ==========
echo [2/5] 检查前端依赖...
if not exist "frontend\node_modules" (
    echo       首次运行，安装前端依赖...
    pushd frontend
    call npm install
    popd
)

REM ========== 3.5 手机模式：提前取局域网 IP（放在括号块外，避免变量展开问题）==========
set "LANIP="
if "%PHONE_MODE%"=="1" (
    echo       正在获取局域网 IP...
    powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp | Select-Object -First 1 -ExpandProperty IPAddress" > "%TEMP%\_gofl_lan_ip.txt" 2>nul
    if exist "%TEMP%\_gofl_lan_ip.txt" set /p LANIP=<"%TEMP%\_gofl_lan_ip.txt"
    del "%TEMP%\_gofl_lan_ip.txt" >nul 2>nul
)

REM ========== 4. 启动后端 ==========
echo [3/5] 启动后端 http://127.0.0.1:8000 ...
start "game-life-backend" /d "%~dp0" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

REM ========== 5. 启动前端 ==========
if "%PHONE_MODE%"=="1" (
    echo [4/5] 启动前端（局域网模式，--host 对本网络开放）...
    start "game-life-frontend" /d "%~dp0frontend" cmd /k "npm run dev -- --host"
) else (
    echo [4/5] 启动前端 http://127.0.0.1:5173 ...
    start "game-life-frontend" /d "%~dp0frontend" cmd /k "npm run dev"
)

REM ========== 6. 打开浏览器并提示手机地址 ==========
echo [5/5] 等待服务就绪，自动打开浏览器...
timeout /t 6 /nobreak >nul
start "" http://127.0.0.1:5173

echo.
echo ============================================
echo   启动完成！
if "%PHONE_MODE%"=="1" (
    echo.
    echo   【本机】http://127.0.0.1:5173
    if defined LANIP (
        echo   【手机】http://%LANIP%:5173
        echo.
        echo   手机需与电脑连同一个 WiFi。
        echo   首次访问若弹出防火墙询问，请选择「允许」。
    ) else (
        echo   【手机】未检测到局域网 IP
        echo   请确认电脑已连接 WiFi 或网线后，重新运行本脚本。
    )
    echo.
    echo   提示：记录都存在本电脑的 game_of_life.db 里，手机不存数据。
) else (
    echo   后端健康检查：http://127.0.0.1:8000/api/health
    echo.
    echo   想用手机记录？关闭后双击 start-phone.bat 即可。
)
echo.
echo   关闭两个 game-life-* 窗口即可停止服务
echo ============================================
echo.
pause
