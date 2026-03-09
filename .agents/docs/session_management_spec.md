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
- `sessionMaxMessages`：触发普通会话清理的阈值（调优值为 60）。
- `sessionClearToSize`：普通会话清理后保留的消息条数（调优值为 40）。
- `sessionBackgroundMaxMessages`：**后台(Heartbeat/Cron)会话**的裁剪阈值（推荐 100 条）。
- `sessionBackgroundClearToSize`：**后台会话**裁剪后保留条数（推荐 50 条），仅保留少量跨周期经验。
- `sessionBackgroundCleanupDays`：后台僵尸会话文件的物理清理周期（默认 15 天）。

### 4.2 清理策略
- **LIFO (后进先出)**：保留时间戳最晚的消息。
- **差异化路由**：系统自动识别 `heartbeat` 或 `cron:` 前缀的 Session Key，应用更激进的后台裁剪参数以节省 Token。
- **物理截断对冲 (Scheme N: ID-Based Anchor)**：
    - **遗留问题**：传统的绝对整数索引 `last_consolidated` 会因为物理截断（从 90 裁至 40）导致数组下标越位而失效。
    - **解决方案**：引入 `last_consolidated_id` 锚点机制。每次获取未归档消息时，动态在数组中定位该 ID 的下标，作为切片起点。
    - **安全气囊**：引入 `sessionSafeBuffer` (默认 20)，确保最新鲜的消息始终不被归档，维持大模型短期记忆的精确性。
- **物理清理 (Harvesting)**：在每次执行后台任务时，系统自动扫描并删除超过 `CleanupDays` 未修改的 `.jsonl` 文件。

## 5. 已知技术修复与决策 (Hotfixes & ADR)
- **标识符规范**：Session 库统一使用 `session.key` 作为标识属性，禁止使用已废弃的 `session_key` 属性。
- **彻底废除幽灵索引 (V10)**：系统中已彻底删除整数型 `last_consolidated` 字段。所有涉及数组切片的逻辑（包括 `/new` 指令）全面转为基于 ID 锚点的动态下标推导，消除了物理修剪后的数组越位爆炸风险。
- **归档强制推进决策**：即使 LLM 认为当前对话片段无提取价值（未调用存储工具），系统也必须强制将 ID 锚点推进至待归档片段的末尾，严禁原地停留，以防产生“算力黑洞”死循环。
- **后台异常守卫**：`create_task` 创建的归档协程必须配备顶层 `try...except` 记录至 logger，防止静默崩溃导致系统游标永久失效。
- **配置读取**：相关参数直接在 `AgentLoop` 初始化时从 `config.json` 获取并注入，不再依赖中间层动态查找。

## 6. 历史消息智能降噪 (Phase 27)
为了释放 Token 空间并提高注意力，系统在 `get_history` 时执行：
- **超长文本硬裁剪**：针对非本次论次关联的消息（i < len - 2 偏离），若 `role == "tool"` 且长度 > 1500 字节，仅保留前 1000 字节。
- **截断标注**：在裁剪处添加 `[... Content truncated for brevity by Staff context manager ...]`，使 LLM 知晓缺失部分为冗余历史。
