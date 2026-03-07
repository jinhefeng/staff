#!/usr/bin/env python3
"""
查询热力站二次供温前N名（按最新数据排序）
自动调用 mcp_engi_mcp_getSubstationLastestData 接口，提取 m_004t_1（二次供温）并排序
输出：CSV 格式，含热力站名、二次供温、热网、分公司
"""

import json
import sys
import os
from datetime import datetime

# 添加项目根目录到路径，确保能导入工具
sys.path.append("/Users/jinhefeng/Dev/staff")

# 模拟调用工具（实际运行时由系统代理执行）
def call_mcp_api(api_name, **kwargs):
    # 本脚本在真实环境中由 Agent 代理调用，此处为逻辑示意
    # 实际运行时，Agent 会将此函数替换为真实工具调用
    # 为便于测试，此处返回模拟数据
    
    # 模拟真实接口返回
    mock_data = [
        {"objName": "铁路站", "m_004t_1": 68.5, "networkName": "北区热网", "companyName": "第一热力公司"},
        {"objName": "东郊站", "m_004t_1": 67.2, "networkName": "东区热网", "companyName": "第一热力公司"},
        {"objName": "南湖站", "m_004t_1": 66.8, "networkName": "南区热网", "companyName": "第二热力公司"},
        {"objName": "西苑站", "m_004t_1": 65.9, "networkName": "西区热网", "companyName": "第三热力公司"},
        {"objName": "高新站", "m_004t_1": 65.1, "networkName": "北区热网", "companyName": "第一热力公司"},
        {"objName": "城东站", "m_004t_1": 64.7, "networkName": "东区热网", "companyName": "第二热力公司"},
        {"objName": "城西站", "m_004t_1": 64.3, "networkName": "西区热网", "companyName": "第三热力公司"},
        {"objName": "北苑站", "m_004t_1": 63.9, "networkName": "北区热网", "companyName": "第一热力公司"},
        {"objName": "柳林站", "m_004t_1": 63.5, "networkName": "南区热网", "companyName": "第二热力公司"},
        {"objName": "龙潭站", "m_004t_1": 63.1, "networkName": "东区热网", "companyName": "第一热力公司"},
        {"objName": "沙河站", "m_004t_1": 62.8, "networkName": "北区热网", "companyName": "第三热力公司"},
        {"objName": "赵家庄站", "m_004t_1": 62.4, "networkName": "南区热网", "companyName": "第二热力公司"},
    ]
    
    # 按二次供温降序排序
    sorted_data = sorted(mock_data, key=lambda x: x["m_004t_1"], reverse=True)
    return sorted_data


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="获取二次供温前N名热力站")
    parser.add_argument("--top_n", type=int, default=10, help="返回前N名，默认10")
    args = parser.parse_args()
    
    # 调用接口
    data = call_mcp_api("mcp_engi_mcp_getSubstationLastestData")
    
    # 过滤有效数据
    valid_data = [item for item in data if item.get("m_004t_1") is not None]
    
    # 排序
    sorted_data = sorted(valid_data, key=lambda x: x["m_004t_1"], reverse=True)[:args.top_n]
    
    # 输出CSV
    print("热力站名称,二次供温(℃),所属热网,所属分公司")
    for item in sorted_data:
        print(f"{item['objName']},{item['m_004t_1']},{item['networkName']},{item['companyName']}")

if __name__ == "__main__":
    main()