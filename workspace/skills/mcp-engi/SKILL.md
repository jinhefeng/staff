name: mcp-engi
description: 封装MCP-ENGI供热系统接口，提供标准化调用方式与常用分析模板。适用于：查询热力站实时/历史数据、排序TOP N站点、生成负荷预测、验证token有效性等。触发场景：当用户要求分析热力站温度、流量、负荷、二次供温排名、热网预测等MCP系统数据时使用。

## 使用指南

本技能封装了所有 `mcp_engi_mcp_*` 接口，避免手动拼接 token/modelType。所有调用均自动继承系统预配置凭证。

### 核心功能模板

#### 1. 查询热力站二次供温前 N 名（推荐）
```bash
scripts/query_top20_secondary_temp.py --top_n 10
```
输出格式：
| 热力站名称 | 二次供温(℃) | 所属热网 | 所属分公司 |

#### 2. 获取指定热力站历史数据
```bash
mcp_engi_mcp_getSubstationHistoryData(objName="铁路站", startTime="2026-03-07 00:00:00", endTime="2026-03-07 23:59:59")
```

#### 3. 获取热网全天负荷预测
```bash
mcp_engi_mcp_get_network_forecast(networkId=1, startTime="2026-03-07T00:00:00", endTime="2026-03-07T23:59:59")
```

#### 4. 验证当前token有效性（自动重试）
```bash
mcp_engi_mcp_get_substation_pid_info()
```

### 注意事项
- 所有接口参数请严格按文档填写，`token` 和 `modelType` 无需手动传入，系统已注入。
- 若返回空或错误，请先运行 `query_top20_secondary_temp.py` 验证系统连通性。
- 所有脚本默认输出为 CSV 格式，可直接导入 Excel 或用于图表生成。

### 常见需求示例
- "帮我看看今天二次供温最高的10个热力站是哪些？" → 使用模板1
- "查一下铁路站昨天的供温曲线" → 使用模板2
- "预测明天整个热网的负荷趋势" → 使用模板3

> 💡 提示：本技能不暴露原始接口细节，只提供业务语义化操作，降低使用门槛。