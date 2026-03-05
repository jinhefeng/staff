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
        "url": "http://172.16.1.105:31916/sse"
      }
    }
  }
}
```

- **服务器名称**: `engi_mcp`
- **连接协议**: SSE (Server-Sent Events) Over HTTP
- **端点地址**: `http://172.16.1.105:31916/sse`

## 3. UI/交互流程
集成后，AI 代理在处理相关请求时，会自动通过该 MCP 服务器发现并调用其提供的工具。用户无需额外手动操作。

## 4. 边缘案例处理
- **网络不可达**: 如果 MCP 服务器宕机或网络无法连通，系统应记录错误并降级到本地工具，而不应导致整个 Agent 崩溃。
- **超时控制**: 目前配置中默认 `toolTimeout` 为 30 秒（参考 `schema.py`）。
