#!/bin/bash

# 数字人应用一键启动脚本

set -e  # 遇到错误立即退出

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 启动数字人应用...${NC}"

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 检查并创建后端虚拟环境
if [ ! -d "backend/venv" ]; then
    echo -e "${YELLOW}📦 创建后端虚拟环境...${NC}"
    cd backend
    python3 -m venv venv
    echo -e "${YELLOW}📦 安装后端依赖...${NC}"
    venv/bin/python -m pip install --quiet -r requirements.txt
    cd ..
else
    # 检查依赖是否已安装（检查 uvicorn 是否存在）
    if ! backend/venv/bin/python -c "import uvicorn" 2>/dev/null; then
        echo -e "${YELLOW}📦 检测到依赖未安装，正在安装后端依赖...${NC}"
        cd backend
        venv/bin/python -m pip install --quiet -r requirements.txt
        cd ..
    fi
fi

# 额外检查关键依赖（如 Edge TTS / miniaudio），避免缺包导致 TTS 不出声
BACKEND_PY="$SCRIPT_DIR/backend/venv/bin/python"
if [ -f "$BACKEND_PY" ]; then
    missing_deps=0
    for module in uvicorn fastapi edge_tts miniaudio; do
        if ! "$BACKEND_PY" -c "import $module" >/dev/null 2>&1; then
            missing_deps=1
            break
        fi
    done
    if [ "$missing_deps" -eq 1 ]; then
        echo -e "${YELLOW}📦 检测到关键依赖缺失，重新安装后端依赖...${NC}"
        cd backend
        "$BACKEND_PY" -m pip install --quiet -r requirements.txt
        cd ..
    fi
fi

# 检查 npm 是否可用
if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ npm 未找到，请先安装 Node.js 和 npm${NC}"
    echo -e "${YELLOW}安装命令:${NC}"
    echo -e "  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -"
    echo -e "  apt-get install -y nodejs"
    exit 1
fi

# 检查并安装前端依赖
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}📦 安装前端依赖...${NC}"
    cd frontend
    npm install --silent
    # 修复可能的权限问题（esbuild 等二进制文件需要执行权限）
    find node_modules -name "esbuild" -type f -exec chmod +x {} \; 2>/dev/null
    chmod +x node_modules/.bin/* 2>/dev/null
    cd ..
fi

# 校验 esbuild 平台二进制是否可用（避免 node_modules 跨平台拷贝导致启动失败）
echo -e "${BLUE}🔍 检查前端 esbuild 环境...${NC}"
cd frontend
if ! node -e "require('esbuild')" >/dev/null 2>&1; then
    echo -e "${YELLOW}📦 检测到 esbuild 平台不匹配，正在重建...${NC}"
    npm rebuild esbuild --silent || npm install --silent
    # 重新检查，若仍失败则执行完整安装
    if ! node -e "require('esbuild')" >/dev/null 2>&1; then
        echo -e "${YELLOW}📦 重建失败，执行完整前端依赖安装...${NC}"
        npm install --silent
    fi
fi
cd ..

# 清理函数
cleanup() {
    echo -e "\n${YELLOW}🛑 正在停止服务...${NC}"
    
    # 停止后端进程
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
        echo -e "${GREEN}✅ 后端服务已停止${NC}"
    fi
    
    # 停止前端进程
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
        echo -e "${GREEN}✅ 前端服务已停止${NC}"
    fi
    
    # 清理可能的残留进程
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    
    exit 0
}

# 注册清理函数，捕获 Ctrl+C
trap cleanup SIGINT SIGTERM

# 启动前清理残留端口占用（避免 Address already in use）
echo -e "${BLUE}🧹 检查并清理残留端口占用...${NC}"
for PORT in 8000 5173; do
    PIDS=$(lsof -ti:$PORT 2>/dev/null || true)
    if [ ! -z "$PIDS" ]; then
        echo -e "${YELLOW}⚠️  端口 $PORT 已被占用，正在释放...${NC}"
        for PID in $PIDS; do
            kill $PID 2>/dev/null || true
        done
        sleep 1
        # 若仍占用则强制结束
        REMAINING_PIDS=$(lsof -ti:$PORT 2>/dev/null || true)
        if [ ! -z "$REMAINING_PIDS" ]; then
            for PID in $REMAINING_PIDS; do
                kill -9 $PID 2>/dev/null || true
            done
        fi
    fi
done

# 启动后端服务
echo -e "${BLUE}🔧 启动后端服务...${NC}"
cd backend
# 使用虚拟环境中 python 的绝对路径，确保 nohup 使用正确的环境
VENV_PYTHON="$SCRIPT_DIR/backend/venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${RED}❌ 虚拟环境 Python 不存在: $VENV_PYTHON${NC}"
    exit 1
fi
nohup "$VENV_PYTHON" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# 等待后端启动
sleep 3

# 检查后端是否启动成功
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}❌ 后端启动失败，请查看 backend.log${NC}"
    tail -20 backend.log
    exit 1
fi

# 验证后端健康状态
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 后端服务已启动 (PID: $BACKEND_PID) - http://localhost:8000${NC}"
else
    echo -e "${YELLOW}⏳ 后端服务启动中...${NC}"
fi

# 启动前端服务
echo -e "${BLUE}🎨 启动前端服务...${NC}"
cd frontend
npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

# 等待前端启动
sleep 5

# 检查前端是否启动成功
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo -e "${RED}❌ 前端启动失败，请查看 frontend.log${NC}"
    tail -20 frontend.log
    cleanup
    exit 1
fi

# 验证前端服务
if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 前端服务已启动 (PID: $FRONTEND_PID) - http://localhost:5173${NC}"
else
    echo -e "${YELLOW}⏳ 前端服务启动中...${NC}"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  🎉 应用启动成功！${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}后端 API:${NC}  http://localhost:8000"
echo -e "  ${BLUE}前端应用:${NC} http://localhost:5173"
echo -e "  ${BLUE}API 文档:${NC} http://localhost:8000/docs"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止所有服务${NC}"
echo ""

# 显示日志（可选）
echo -e "${YELLOW}💡 提示: 查看日志文件:${NC}"
echo -e "  - 后端日志: ${BLUE}tail -f backend.log${NC}"
echo -e "  - 前端日志: ${BLUE}tail -f frontend.log${NC}"
echo ""

# 等待用户中断
wait
