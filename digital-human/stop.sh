#!/bin/bash

# 数字人应用停止脚本

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛑 正在停止数字人应用服务...${NC}"
echo ""

# 停止后端服务 (端口 8000)
echo -e "${YELLOW}停止后端服务 (端口 8000)...${NC}"
BACKEND_PIDS=$(lsof -ti:8000 2>/dev/null)
if [ ! -z "$BACKEND_PIDS" ]; then
    for PID in $BACKEND_PIDS; do
        kill $PID 2>/dev/null && echo -e "  ${GREEN}✅ 已停止进程 $PID${NC}" || echo -e "  ${RED}❌ 无法停止进程 $PID${NC}"
    done
    sleep 1
    # 强制杀死仍在运行的进程
    lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null
else
    echo -e "  ${YELLOW}⚠️  未发现运行在 8000 端口的进程${NC}"
fi

# 停止前端服务 (端口 5173)
echo -e "${YELLOW}停止前端服务 (端口 5173)...${NC}"
FRONTEND_PIDS=$(lsof -ti:5173 2>/dev/null)
if [ ! -z "$FRONTEND_PIDS" ]; then
    for PID in $FRONTEND_PIDS; do
        kill $PID 2>/dev/null && echo -e "  ${GREEN}✅ 已停止进程 $PID${NC}" || echo -e "  ${RED}❌ 无法停止进程 $PID${NC}"
    done
    sleep 1
    # 强制杀死仍在运行的进程
    lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null
else
    echo -e "  ${YELLOW}⚠️  未发现运行在 5173 端口的进程${NC}"
fi

# 停止 uvicorn 相关进程
echo -e "${YELLOW}清理 uvicorn 进程...${NC}"
UVICORN_PIDS=$(pgrep -f "uvicorn app.main:app" 2>/dev/null)
if [ ! -z "$UVICORN_PIDS" ]; then
    for PID in $UVICORN_PIDS; do
        kill $PID 2>/dev/null && echo -e "  ${GREEN}✅ 已停止 uvicorn 进程 $PID${NC}" || echo -e "  ${RED}❌ 无法停止进程 $PID${NC}"
    done
    sleep 1
    pgrep -f "uvicorn app.main:app" 2>/dev/null | xargs kill -9 2>/dev/null
fi

# 停止 vite 相关进程
echo -e "${YELLOW}清理 vite 进程...${NC}"
VITE_PIDS=$(pgrep -f "vite" 2>/dev/null)
if [ ! -z "$VITE_PIDS" ]; then
    for PID in $VITE_PIDS; do
        # 排除其他可能的 vite 进程，只停止我们的
        if ps -p $PID -o command= | grep -q "digital-human\|node.*vite"; then
            kill $PID 2>/dev/null && echo -e "  ${GREEN}✅ 已停止 vite 进程 $PID${NC}" || echo -e "  ${RED}❌ 无法停止进程 $PID${NC}"
        fi
    done
    sleep 1
fi

# 停止 npm run dev 相关进程
echo -e "${YELLOW}清理 npm 进程...${NC}"
NPM_PIDS=$(pgrep -f "npm run dev" 2>/dev/null)
if [ ! -z "$NPM_PIDS" ]; then
    for PID in $NPM_PIDS; do
        kill $PID 2>/dev/null && echo -e "  ${GREEN}✅ 已停止 npm 进程 $PID${NC}" || echo -e "  ${RED}❌ 无法停止进程 $PID${NC}"
    done
    sleep 1
fi

# 清理日志文件（可选）
read -p "$(echo -e ${YELLOW}是否清理日志文件? [y/N]: ${NC})" -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}清理日志文件...${NC}"
    [ -f "backend.log" ] && rm backend.log && echo -e "  ${GREEN}✅ 已删除 backend.log${NC}"
    [ -f "frontend.log" ] && rm frontend.log && echo -e "  ${GREEN}✅ 已删除 frontend.log${NC}"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ 所有服务已停止${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""

# 验证端口是否已释放
echo -e "${BLUE}验证端口状态:${NC}"
if lsof -ti:8000 > /dev/null 2>&1; then
    echo -e "  ${RED}❌ 端口 8000 仍被占用${NC}"
else
    echo -e "  ${GREEN}✅ 端口 8000 已释放${NC}"
fi

if lsof -ti:5173 > /dev/null 2>&1; then
    echo -e "  ${RED}❌ 端口 5173 仍被占用${NC}"
else
    echo -e "  ${GREEN}✅ 端口 5173 已释放${NC}"
fi

echo ""

