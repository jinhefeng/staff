# Session 会话管理设计规范 v1.0

## 1. 核心定义
Session 是以 `channel:chat_id` 为唯一标识的持久化对话历史，存储在 `sessions/` 目录下（格式为 `.jsonl`）。
- **生命周期**：随消息产生而自动创建，随存储治理规则自动裁剪。
- **并发控制**：使用 `AgentLoop` 内部的 `_consolidation_locks` (asyncio.Lock) 确保同一会话的消息处理顺序性和文件写入安全性。

## 2. 消息存储规范 (Phase L/M 优化)
为了降低存储开销并精简上下文，Session 遵循以下字段过滤规则：

### 2.1 User 消息
- **元数据裁剪**：移除冗余字段（如 `platform`, `conversation_title`, `conversation_type`）。
- **字段差异性**：
  - **私聊 (Private)**：仅保存 `role`, `content`, `timestamp`, `metadata(dingtalk_msg_id, quote_msg_id)`。
  - **群聊 (Group)**：额外保存 `metadata(sender_name, sender_id)` 以识别发言人。

### 2.2 Assistant 消息
- **裁剪内容**：移除 `correlation_id` 以节省空间。

## 3. 引用上下文逻辑 (Quote Context Handling)
当用户引用消息（回复消息）时，系统执行递归搜索以重建讨论链：

### 3.1 搜索机制
- **递归查找**：通过 `quote_msg_id` 匹配 Session 历史中的 `dingtalk_msg_id`。
- **多级嵌套**：如果被引用的消息本身也引用了更早的消息，继续向上溯源。

### 3.2 场景差异化路由
- **私聊场景**：**仅支持向上搜索**。即仅查找当前讨论链的祖先消息，避免上下文污染。
- **群聊场景**：**支持双向匹配**。按时间顺序排列所有关联消息（包括多人对同一消息的回复），以明确复杂讨论的时间线。

## 4. 存储治理机制 (Scheme O)
为防止 Session 文件无限膨胀，系统执行自动清理：

### 4.1 配置参数 (`config.json`)
- `sessionMaxMessages`：触发清理的阈值（如超过 500 条）。
- `sessionClearToSize`：清理后保留的消息条数（如保留最新的 300 条）。

### 4.2 清理策略
- **LIFO (后进先出)**：保留时间戳最晚的消息。
- **原子性**：清理操作在 `AgentLoop._prune_session_if_needed` 中执行，确保文件操作的完整性。

## 5. 已知技术修复 (Hotfixes)
- **标识符规范**：Session 库统一使用 `session.key` 作为标识属性，禁止使用已废弃的 `session_key` 属性。
- **配置读取**：相关参数直接在 `AgentLoop` 初始化时从 `config.json` 获取并注入，不再依赖中间层动态查找。
