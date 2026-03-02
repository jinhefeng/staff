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
# 通过向 nanobot 注入 ENV 指针，将系统加载路径强行锚定在本项目内的 config.json
export NANOBOT_CONFIG_PATH="$CONFIG_FILE"

# 【混合架构桥梁】将本地运行环境的网关指向本机的 Docker Gewechat 容器
export GEWE_BASE_URL="http://127.0.0.1:2531"

# 剥离杂项守护，使用本隔离境拉起
python -m nanobot gateway
