# 钉钉入站消息完整数据说明 (DingTalk Inbound Data Spec)

在 Staff 系统中，钉钉消息通过 **DingTalk Stream Mode** 接收。当一条消息到达时，系统会捕获一个完整的 JSON Payload。以下是该数据的详细流转说明。

## 1. 原始数据 (Raw Data)
当钉钉向机器人发送消息时，`dingtalk-stream` SDK 会接收到一个 `CallbackMessage`。其核心内容存储在 `message.data` 中。

### 典型 JSON 示例 (群聊/引用场景)
```json
{
  "msgId": "msgXXXXXXXXXXXX",
  "createAt": 1709999999000,
  "conversationType": "2",
  "openConversationId": "cidXXXXXXXX",
  "conversationTitle": "Staff 研发群",
  "senderId": "user123",
  "senderStaffId": "014224562537153949",
  "senderNick": "张三",
  "isAdmin": true,
  "msgType": "text",
  "text": {
    "content": "帮我看看这个工单 @机器人",
    "isReplyMsg": true,
    "repliedMsg": {
      "msgId": "msgYYYYYYYYYYYY",
      "senderId": "robot456",
      "senderNick": "Staff-Assistant",
      "content": "{\"text\": \"这是之前的卡片内容...\"}"
    }
  },
  "atUsers": [
    {
      "dingtalkId": "robot456",
      "staffId": ""
    }
  ],
  "chatbotUserId": "robot456",
  "extensions": {
    "originalMsgId": "msgYYYYYYYYYYYY"
  }
}
```

## 2. 系统内部映射 (Internal Mapping)
在 `nanobot/channels/dingtalk.py` 中，上述数据被转换为通用的 `InboundMessage` 对象。

| 原始字段 | 映射到 `InboundMessage` | 说明 |
| :--- | :--- | :--- |
| `text.content` | `content` | 剥离 @ 后的纯文本内容 |
| `senderStaffId` / `senderId` | `sender_id` | 优先使用工号 (StaffId) |
| `openConversationId` | `chat_id` | 群聊使用 OpenConvId，私聊使用 SenderId |
| `msgId` | `metadata.dingtalk_msg_id` | 钉钉原始消息唯一标识 |
| `conversationType` | `metadata.conversation_type` | "1" 代表私聊，"2" 代表群聊 |
| `senderNick` | `metadata.sender_name` | 发送者昵称 |

### 特殊处理：引用上下文 (Quote Context)
如果消息包含引用（`isReplyMsg: true`），系统会执行以下逻辑并注入 `metadata`：
- `metadata.quote_msg_id`: 被引用消息的 ID。
- `metadata.quote_text`: 自动从 `repliedMsg` 中提取的文本。
- `metadata.quote_sender`: 被引用者的昵称。

## 3. 如何查看实时完整信息
如果你想在调试时看到每一条消息的完整“真身”，可以查看运行日志（`./start.sh` 输出或日志文件）：

搜索关键词: `DEBUG: DingTalk Inbound message.data`

日志示例：
```text
2026-03-09 22:30:00 | DEBUG | NanobotDingTalkHandler:process:57 - DEBUG: DingTalk Inbound message.data: { ... 完整 JSON ... }
```
