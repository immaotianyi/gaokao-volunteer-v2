#!/bin/bash
# 高考志愿狙击手 — 一键启动脚本
# 后端 FastAPI + 前端页面

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
PORT=8000

echo "========================================"
echo "  高考志愿狙击手 — 捡漏雷达"
echo "  广东物理类+历史类 | 2024+2025真实数据"
echo "========================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 需要 Python 3.9+"
    exit 1
fi

# 检查依赖
echo "[1/3] 检查依赖..."
cd "$BACKEND_DIR"
python3 -c "import fastapi, pandas, pdfplumber" 2>/dev/null || {
    echo "  安装依赖..."
    pip3 install -q fastapi uvicorn pandas pdfplumber pydantic redis httpx 2>&1 | tail -1
}
echo "  ✅ 依赖就绪"

# 检查数据
echo "[2/3] 检查数据..."
for f in plans_2024.csv plans_2025.csv admission_history.csv; do
    if [ -f "data/$f" ]; then
        ROWS=$(wc -l < "data/$f" | tr -d ' ')
        echo "  ✅ data/$f ($ROWS 行)"
    else
        echo "  ❌ data/$f 缺失"
        exit 1
    fi
done

# 启动后端
echo "[3/3] 启动服务..."
echo ""
echo "  Vue3 前端:  cd frontend && npm run dev"
echo "  旧版入口:   http://localhost:$PORT/demo.html"
echo "  API 文档:   http://localhost:$PORT/docs"
echo ""
echo "  按 Ctrl+C 停止"
echo "========================================"
echo ""

cd "$BACKEND_DIR"
python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT --reload
