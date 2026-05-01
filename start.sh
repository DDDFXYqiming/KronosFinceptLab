#!/bin/bash
# KronosFinceptLab 一键启动脚本
# 同时启动 API 后端和 Web 前端

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}KronosFinceptLab 启动中...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}警告: 找不到 python3，尝试使用 Windows Python${NC}"
    PYTHON="python"
else
    PYTHON="python3"
fi

# 检查 node
if ! command -v node &> /dev/null; then
    echo -e "${YELLOW}错误: 找不到 node，请先安装 Node.js${NC}"
    exit 1
fi

# 检查 npm
if ! command -v npm &> /dev/null; then
    echo -e "${YELLOW}错误: 找不到 npm，请先安装 Node.js${NC}"
    exit 1
fi

# 检查 web/node_modules
if [ ! -d "web/node_modules" ]; then
    echo -e "${YELLOW}安装前端依赖...${NC}"
    cd web
    npm install
    cd ..
fi

# 启动 API 后端
echo -e "${GREEN}[1/2] 启动 API 后端...${NC}"
echo -e "      地址: http://localhost:8000"
echo -e "      文档: http://localhost:8000/docs"
echo ""

PYTHONPATH=src $PYTHON -m kronos_fincept.api.app &
API_PID=$!

# 等待 API 启动
sleep 2

# 检查 API 是否运行
if kill -0 $API_PID 2>/dev/null; then
    echo -e "${GREEN}      API 后端启动成功${NC}"
else
    echo -e "${YELLOW}      API 后端启动失败${NC}"
fi

echo ""

# 启动 Web 前端
echo -e "${GREEN}[2/2] 启动 Web 前端...${NC}"
echo -e "      地址: http://localhost:3000"
echo ""

cd web
npm run dev &
WEB_PID=$!
cd ..

# 等待前端启动
sleep 3

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}启动完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "API 后端: ${GREEN}http://localhost:8000${NC}"
echo -e "Web 前端: ${GREEN}http://localhost:3000${NC}"
echo -e "API 文档: ${GREEN}http://localhost:8000/docs${NC}"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止所有服务${NC}"
echo ""

# 优雅退出
cleanup() {
    echo ""
    echo -e "${YELLOW}正在停止服务...${NC}"
    kill $API_PID 2>/dev/null || true
    kill $WEB_PID 2>/dev/null || true
    echo -e "${GREEN}已停止所有服务${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 等待任意进程退出
wait
