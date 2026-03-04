#!/bin/bash
set -e

echo "=========================================="
echo "    启动 Staff 智能幕僚 (Powered by nanobot)"
echo "=========================================="

echo "[1/4] 检查虚拟运行环境..."
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "🚨 [错误] 缺失核心虚拟运行环境！"
    echo "👉 请您先执行环境部署构建工具： ./install.sh"
    exit 1
fi
echo ">> 环境目录就绪。"

echo "[2/4] 安全激活隔离域保护..."
source "$VENV_DIR/bin/activate"

echo "[3/4] 验证纯本地配置文件 (Local config.json)..."
CONFIG_FILE="$PWD/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo ">> 未发现本地私有配置 config.json，正在根据样本模板为您生成..."
    cp config.sample.json "$CONFIG_FILE"
    echo ""
    echo "🚨 [拦截] 核心配置模板已落盘到本目录下的 config.json！"
    echo "由于安全原因，请您手动打开文件，将其中的 api_key 等参数替换为您真实的凭据。"
    echo ">> (此私有文件已被添加到 .gitignore 并屏蔽上传)"
    echo "修改完毕后，请再次运行本脚本启动系统。"
    exit 1
fi
echo ">> 私有配置探测通过。"

echo "[4/4] 环境挂载成功，即将拉起微服务核心..."
echo "=========================================="
# 安全重启：检测并清理后台残留的 gateway 进程
EXISTING_PID=$(pgrep -f "python.*nanobot gateway" || true)
if [ -n "$EXISTING_PID" ]; then
    echo -e "\033[33m⚠️ 检测到残留 gateway 进程 (PID: $EXISTING_PID)，正在清理...\033[0m"
    pkill -f "python.*nanobot gateway" || true
    # 循环等待进程完全退出，最多等 10 秒
    for i in $(seq 1 10); do
        if ! pgrep -f "python.*nanobot gateway" > /dev/null 2>&1; then
            echo -e "\033[32m✅ 旧进程已全部清理完毕。\033[0m"
            break
        fi
        # 5 秒后升级为 SIGKILL 强制终止
        if [ "$i" -eq 5 ]; then
            echo -e "\033[31m   旧进程未响应 SIGTERM，发送 SIGKILL 强制终止...\033[0m"
            pkill -9 -f "python.*nanobot gateway" || true
        fi
        sleep 1
    done
    # 最终兜底检查
    if pgrep -f "python.*nanobot gateway" > /dev/null 2>&1; then
        echo -e "\033[31m🚨 [错误] 无法清理残留进程，请手动执行: kill -9 $EXISTING_PID\033[0m"
        exit 1
    fi
fi

# 通过向 nanobot 注入 ENV 指针，将系统加载路径强行锚定在本项目内的 config.json
export NANOBOT_CONFIG_PATH="$CONFIG_FILE"

# 剥离杂项守护，使用本隔离境拉起
python -m nanobot gateway
