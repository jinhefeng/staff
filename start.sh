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
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            echo -e "\033[33m⚠️ 发现 PID:$OLD_PID 正在运行，强制执行斩首行动...\033[0m"
            kill -9 "$OLD_PID" || true
            sleep 1
        fi
        rm -f "$PID_FILE"
    fi
    # 模糊匹配残留兜底
    REMAINING=$(pgrep -f "python.*nanobot gateway" || true)
    if [ -n "$REMAINING" ]; then
        echo -e "\033[31m⚠️ 发现模糊匹配残留进程 ($REMAINING)，一并清理...\033[0m"
        pkill -9 -f "python.*nanobot gateway" || true
    fi
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

check_running

# 4. 抢占原子锁
if ! mkdir "$LOCK_FILE" 2>/dev/null; then
    echo "🚨 [并发冲突] 锁定失败，可能已有其他实例正在启动。"
    exit 1
fi

# 确保退出时清理锁目录
trap 'rm -rf "$LOCK_FILE"; exit' INT TERM EXIT

kill_existing

echo "[1/2] 激活隔离域并挂载配置..."
source "$VENV_DIR/bin/activate"
export NANOBOT_CONFIG_PATH="$CONFIG_FILE"

echo "[2/2] 启动幕僚核心 (调试前台模式)..."
# 纯前台阻塞运行，Ctrl+C 会一并结束 python 并触发 start.sh 的 trap 回收锁
python -m nanobot gateway


