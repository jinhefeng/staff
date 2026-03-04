#!/bin/bash
set -e

echo "=========================================="
echo "    智能幕僚 (Staff) 环境部署构建工具"
echo "=========================================="

echo "[阶段 1/4] 寻找合适的 Python3 解释器..."
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    if python -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' &> /dev/null; then
        PYTHON_CMD="python"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "🚨 错误: 未能在系统中找到适合的 python3 (此架构依赖 Python 3.10+)。"
    exit 1
fi
echo ">> 使用解释器: $(command -v $PYTHON_CMD) ($($PYTHON_CMD --version))"

echo "[阶段 2/4] 构建虚拟隔离环境 (venv)..."
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo ">> 正在您的项目目录创建完全隔离的虚拟空间，这大概需要几秒钟..."
    $PYTHON_CMD -m venv "$VENV_DIR"
else
    echo ">> 发现已存在的 venv，跳过创建。"
fi

echo "[阶段 3/4] 激活环境并更新基础组件..."
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip --quiet
echo ">> pip 基础组件升级完毕。"

echo "[阶段 4/4] 正在以开发模式安装 nanobot 智能核心..."
pip install -e . --quiet
echo ">> 核心大脑注入成功。"

echo ""
echo "[额外步骤] 正在为您准备 Systemd 服务配置文件..."
PROJECT_ROOT=$(pwd)
CURRENT_USER=$(whoami)
SERVICE_FILE="staff.service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Staff Intelligent Agent Service
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_ROOT
Environment=NANOBOT_CONFIG_PATH=$PROJECT_ROOT/config.json
ExecStart=$PROJECT_ROOT/venv/bin/python -m nanobot gateway
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo ">> 配置文件已生成: $PROJECT_ROOT/$SERVICE_FILE"

echo "=========================================="
echo "✨ 安装与部署完成，物理环境已隔离！"
echo ""
echo "👉 方式 A: 手动启动"
echo "   运行: ./start.sh"
echo ""
echo "👉 方式 B: 系统服务启动 (Systemd)"
echo "   1. 注册服务: sudo cp $SERVICE_FILE /etc/systemd/system/"
echo "   2. 重载配置: sudo systemctl daemon-reload"
echo "   3. 启动并开机自启:"
echo "      sudo systemctl enable --now staff"
echo "   4. 查看状态: systemctl status staff"
echo "=========================================="
