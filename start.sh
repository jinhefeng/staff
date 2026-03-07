#!/bin/bash
set -e

# 配置区域
VENV_DIR="venv"
PID_FILE=".staff.pid"
LOCK_FILE=".staff.lock"
CONFIG_FILE="$PWD/config.json"

echo "=========================================="
echo "    启动 Staff 智能幕僚 (Powered by nanobot)"
echo "=========================================="

# 1. 环境与配置检查
if [ ! -d "$VENV_DIR" ]; then
    echo "🚨 [错误] 缺失核心虚拟运行环境！请执行 ./install.sh"
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo ">> 正在生成配置样本 config.json..."
    cp config.sample.json "$CONFIG_FILE"
    echo "🚨 [拦截] 请手动修改 config.json 中的凭据后重新启动。"
    exit 1
fi

# 2. 强力清理函数
kill_existing() {
    # 杀掉主程序
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo -e "\033[33m⚠️ 发现主进程 PID:$OLD_PID 正在运行，强制执行斩首行动...\033[0m"
            kill -9 "$OLD_PID" || true
        fi
        rm -f "$PID_FILE"
    fi
    
    # 清理所有 nanobot gateway 残留
    pgrep -f "python.*nanobot gateway" | xargs kill -9 > /dev/null 2>&1 || true
    
    # 清理监控相关
    echo ">> 正在清理监控残存进程 (Port 8880 & monitor_loop)..."
    lsof -ti:8880 | xargs kill -9 > /dev/null 2>&1 || true
    pgrep -f "monitor_loop.sh" | xargs kill -9 > /dev/null 2>&1 || true
    
    # 清理所有残留锁
    rm -rf "$LOCK_FILE"
}

# 3. 运行前检查 (防重开)
check_running() {
    if [ -d "$LOCK_FILE" ]; then
        # 如果锁存在，检查是否有相关进程存活
        LIVE_PID=$(pgrep -f "python.*nanobot gateway" || true)
        if [ -n "$LIVE_PID" ]; then
            echo "🚨 [错误] 系统已在运行中 (PID: $LIVE_PID)，请勿重复启动。"
            exit 1
        else
            echo "⚠️  发现残留 Lock 目录但无存活进程，正在自动回收资源..."
            rm -rf "$LOCK_FILE"
        fi
    fi
}

# 4. 退出清理钩子 (Trap)
cleanup() {
    echo -e "\n\033[32m[终止] 正在关停 Staff 幕僚系统及监控看板...\033[0m"
    # 杀掉当前脚本启动的所有子进程
    pkill -P $$ > /dev/null 2>&1 || true
    # 显式清理端口
    lsof -ti:8880 | xargs kill -9 > /dev/null 2>&1 || true
    # 移除锁
    rm -rf "$LOCK_FILE"
    echo "✨ 环境已清理。"
}

# 挂载钩子
trap cleanup INT TERM EXIT

check_running
kill_existing

echo "[1/3] 激活隔离域并挂载配置..."
source "$VENV_DIR/bin/activate"
export NANOBOT_CONFIG_PATH="$CONFIG_FILE"

echo "[2/3] 启动看板服务 (Background)..."
# 启动监控采集
nohup ./nanobot/utils/monitor_loop.sh > /dev/null 2>&1 &
# 启动 HTTP Server
nohup python3 -m http.server 8880 --directory ./website/monitor > /dev/null 2>&1 &

echo "[3/3] 启动幕僚核心 (调试前台模式)..."
echo ">> 监控面板已就绪: http://localhost:8880"
echo "=========================================="
# 纯前台阻塞运行
python -m nanobot gateway


