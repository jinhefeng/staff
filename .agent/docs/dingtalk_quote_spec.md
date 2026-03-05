# 功能说明书 (Functional Spec) - DingTalk 引用增强 (Session 方案)

## 1. 背景
用户在钉钉中引用 Staff 历史消息（特别是互动卡片）时，由于卡片不含普通文本且 OpenAPI 抓取不稳定，导致 AI 失去上下文。

## 2. 核心逻辑

### 2.1 ID 链路闭环 (The Loopback)
- **发送阶段**：
    - `DingTalkChannel` 在调用 `robot/oToMessages/batchSend` 或 `robot/groupMessages/send` 成功后，提取返回的 `messageId` 或 `processQueryKey`。
    - 发布 `MessageSentEvent` 到内部总线。
- **同步阶段**：
    - `AgentLoop` (或新组件 `SessionWorker`) 监听该事件。
    - 根据事件中的消息指纹（内容哈希+时间戳）找到 Session 中最后一条 `assistant` 消息。
    - 在该消息的 `metadata` 中写入 `dingtalk_msg_id`。

### 2.2 引用识别与回访 (The Retrieval)
- **接收阶段**：
    - 识别到 `repliedMsg.msgId` 后，调用 `SessionManager.find_message_by_metadata(key, "dingtalk_msg_id", msg_id)`。
- **匹配规则**：
    - **单聊**：在本用户 Session 中寻找。
    - **群聊**：在本群 Session 中寻找。
- **优先级**：本地 Session 匹配 (100% 准确) > OpenAPI 抓取 (补充) > 类型占位符 (兜底)。

## 3. 边界情况处理
- **Session 清理**：若用户执行 `/new`，则旧消息 ID 不再保留，此时回退到 API 抓取。
- **多端同步**：若 ID 没能及时写入 Session（如网络延迟），通过 API 进行二次确认。

## 4. 影响分析
- **依赖**：需要修改 `AgentLoop` 监听新事件。
- **冲突**：无明显逻辑冲突。
