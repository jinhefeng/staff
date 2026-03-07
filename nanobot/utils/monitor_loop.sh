#!/bin/bash
# 监控数据循环采集脚本

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$( dirname "$( dirname "$SCRIPT_DIR" )" )"

echo "STAFF 监控系统启动：正在进入循环采集模式..."

while true; do
    # 激活开发环境
    source "$PROJECT_ROOT/venv/bin/activate"
    
    # 运行采集器
    python3 "$SCRIPT_DIR/monitor_collector.py"
    
    echo "数据已更新: $(date)"
    
    # 每 60 秒刷新一次
    sleep 60
done
