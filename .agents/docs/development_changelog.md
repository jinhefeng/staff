# Staff 开发变更日志 (Development Changelog)

> 记录所有阶段的核心变更，供新会话快速恢复上下文。

---

## Phase 25 (2026-03-03 ~ 03-04): 跨会话发消息 + 联系人动态记录

### 核心架构
- **钉钉通讯录扩展**: `DingTalkDirectory` 封装 `/v1.0/contact/users/search`。
- **动态本地区域缓存**:
  - `groups.json` 自动收集团队群组 ID (`openConversationId`) 和 `title` 用于精准查群。
  - 客体专域记忆文件 (Guest Memory) 中加入 `Alias` 记录用于自然语言跨会话发送的别名检索。
- **跨会话 Tool (`send_cross_chat`)**:
  - `TrustScore` 校验 (非 Master 需 >= 85 分才能发送消息至指定会话)。
- **Bug Fix (Guest Memory)**:
  - 群组中的新成员 @Staff 时立即生成 `TrustScore: 50` 的客体记录文件，即使触发条数未满 `memory_window`。

### 变更文件
- `nanobot/channels/directory.py` — 钉钉用户 API 搜索
- `nanobot/agent/tools/cross_chat.py` — `SearchContactsTool`, `SendCrossChatTool`
- `nanobot/agent/memory.py` — 增加读取 `groups.json` 的 API 支持
- `nanobot/agent/loop.py` — 群组 Guest 初始化及群名提取

---

## Phase 22-24 (2026-03-02 ~ 03-03): 钉钉引用 + 安审优化

### 变更文件
- `nanobot/channels/dingtalk.py` — 引用消息三层解析 + per-chat 缓存
- `nanobot/agent/loop.py` — `is_master` 传递到 Sanitizer
- `nanobot/agent/sanitizer.py` — Master 用户安审绕过
- `nanobot/config/schema.py` — `DingTalkConfig` 补全 `master_ids` 字段

### 关键发现
1. **钉钉平台限制**：引用 `interactiveCard` 时 webhook 不携带内容，API 返回 404
2. **引用的引用**：reply-of-reply 场景下钉钉甚至不提供 `repliedMsg` 子对象
3. **`repliedMsg.content` 格式**：文字消息的 content 是 dict `{"text": "xxx"}` 不是 string
4. **Schema 缺失**：`DingTalkConfig` 未定义 `master_ids` 导致 Pydantic 静默丢弃配置值

---

## Phase 19-20 (2026-03-02): 联邦记忆 + 潜意识反思

### 核心架构
- **物理隔离**: `memory/core/global.md` + `memory/guests/{id}.md`
- **YAML Frontmatter**: 每个 Guest 文件头含 `TrustScore: 50`
- **ReflectionAgent**: 后台静默交叉比对 Guest 记忆与全域知识
- **自动化惩罚**: 谣言检测 → TrustScore 降权 → Master 告警

### 变更文件
- `nanobot/agent/memory.py` — 联邦记忆读写
- `nanobot/agent/reflection.py` — 潜意识反思引擎
- `nanobot/agent/context.py` — Master/Guest 双模式 Prompt

---

## Phase 17-18 (2026-03-02): 安审 + 异步工单

### 核心架构
- **三态 Sanitizer**: SAFE / BLOCK / ESCALATE
- **异步工单**: 挂起 → 安抚心跳 → Master 批复 → 闭环
- **`<think>` 清洗**: 兼容 DeepSeek 等推理模型

### 变更文件
- `nanobot/agent/sanitizer.py` — 输入净化 + 输出脱敏
- `nanobot/agent/tickets.py` — 工单管理器
- `nanobot/agent/tools/tickets.py` — Escalate/Resolve 工具

---

## Phase 14-16 (2026-03-01): 钉钉集成 + 记忆标签

### 变更文件
- `nanobot/channels/dingtalk.py` — 首版 DingTalk Stream 接入
- `nanobot/config/schema.py` — DingTalk 配置定义
- `nanobot/templates/SOUL.md` — 人格灵魂 Prompt
