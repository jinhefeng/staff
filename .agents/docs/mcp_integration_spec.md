# 功能说明书: MCP 服务器 (engi_mcp) 集成

## 1. 业务逻辑描述
为了增强 `staff` 系统的工具调用能力，我们需要集成一个外部的 MCP (Model Context Protocol) 服务器。该服务器提供额外的专业工具集。

## 2. 配置定义
在核心配置文件 `config.json` 的 `tools.mcpServers` 路径下集成以下配置：

```json
{
  "tools": {
    "mcpServers": {
      "engi_mcp": {
        "url": "http://172.16.1.105:31916/sse",
        "toolTimeout": 180
      }
    }
  }
}
```

- **服务器名称**: `engi_mcp`
- **连接协议**: SSE (Server-Sent Events) Over HTTP
- **端点地址**: `http://172.16.1.105:31916/sse`
- **超时配置**: `toolTimeout` 支持动态配置，默认为 30s，建议设置为 180s。

## 3. 设计决策 (ADR)
- **动态超时机制**: 为了支持长耗时的工业数据拉取，系统不再硬编码超时。`nanobot/agent/tools/mcp.py` 会动态读取 `toolTimeout` 配置，并同步应用于 SSE 连接建立与工具执行阶段。

## 4. UI/交互流程
集成后，AI 代理在处理相关请求时，会自动通过该 MCP 服务器发现并调用其提供的工具。用户无需额外手动操作。

## 5. 边缘案例处理
- **网络不可达**: 如果 MCP 服务器宕机或网络无法连通，系统应记录错误并降级到本地工具，而不应导致整个 Agent 崩溃。
- **超时取消**: 若工具执行超过设定值，系统将强制终止协程并向 LLM 返回超时错误片段。
