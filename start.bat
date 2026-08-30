@echo off
chcp 65001 >nul
title 游戏人生 · 一键启动
cd /d "%~dp0"

echo ============================================
echo   游戏人生（Game of Life）一键启动
echo ============================================

REM ---- 1. 检查 .env ----
if not exist ".env" (
  echo [1/4] 未找到 .env，正在从 .env.example 复制模板...
  copy ".env.example" ".env" >nul
  echo.
  echo [重要] 已生成 .env，请先编辑填入你的 DeepSeek API Key：
  echo        执行：notepad .env
  pause
  exit /b 1
)

REM ---- 2. 后端依赖 ----
echo [1/4] 检查 Python 依赖...
python -c "import fastapi, uvicorn, sqlalchemy, openai, dotenv" 2>nul
if errorlevel 1 (
  echo        首次运行，安装后端依赖中...
  python -m pip install -r requirements.txt
)

REM ---- 3. 前端依赖 ----
echo [2/4] 检查前端依赖...
if not exist "frontend\node_modules" (
  echo        首次运行，安装前端依赖中...
  pushd frontend
  call npm install
  popd
)

REM ---- 4. 启动后端 ----
echo [3/4] 启动后端（http://127.0.0.1:8000）...
start "游戏人生-后端" cmd /k "cd /d %~dp0 && python -m uvicorn app.main:app --reload --port 8000"

REM ---- 5. 启动前端 ----
echo [4/4] 启动前端（http://127.0.0.1:5173）...
start "游戏人生-前端" cmd /k "cd /d %~dp0frontend && npm run dev"

REM ---- 6. 打开浏览器 ----
echo 等待服务就绪，自动打开浏览器...
timeout /t 6 /nobreak >nul
start http://127.0.0.1:5173

echo.
echo 启动完成！健康检查：http://127.0.0.1:8000/api/health
echo 关闭两个新开的命令行窗口即可停止服务。
pause
