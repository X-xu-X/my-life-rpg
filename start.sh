#!/usr/bin/env bash
# 游戏人生一键启动（Linux/macOS/Git Bash 可用；Windows 请用 start.bat）
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  游戏人生（Game of Life）一键启动"
echo "============================================"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[!] 已生成 .env，请先编辑填入 DeepSeek API Key 后重新运行"
  exit 1
fi

echo "[1/4] 检查 Python 依赖..."
python -c "import fastapi, uvicorn, sqlalchemy, openai, dotenv" 2>/dev/null || pip install -r requirements.txt

echo "[2/4] 检查前端依赖..."
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

echo "[3/4] 启动后端（http://127.0.0.1:8000）..."
(python -m uvicorn app.main:app --reload --port 8000 &)

echo "[4/4] 启动前端（http://127.0.0.1:5173）..."
(cd frontend && npm run dev &)

sleep 6
start http://127.0.0.1:5173 2>/dev/null || open http://127.0.0.1:5173 2>/dev/null || xdg-open http://127.0.0.1:5173 2>/dev/null || true

echo "启动完成！健康检查：http://127.0.0.1:8000/api/health"
