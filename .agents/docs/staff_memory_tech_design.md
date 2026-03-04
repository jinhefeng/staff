# Staff 记忆与安全系统架构技术说明书 v2.0

> 本文档反映 Phase 15-20 全部落地后的最终系统架构。

## 1. 架构总览

```
Guest 输入
   │
   ▼
[Phase 17: Input Sanitizer] ──BLOCK──▶ 外交辞令拒绝
   │                         ──ESCALATE──▶ [Phase 18: 异步工单 + 安抚]
   ▼ (SAFE)
[Phase 16: Guest 行为手册] ──日程窥探──▶ 模糊挡驾
                            ──SOP 关键词──▶ 读取 sop/ 文档返回
                            ──信息留言──▶ 收集后 escalate
                            ──超出职权──▶ escalate + 安抚
   │
   ▼ (正常对话)
[Core Agent + 联邦记忆] ──▶ 生成回复
   │
   ▼
[Phase 17: Output Auditor] ──泄露──▶ 强制重写
   │
   ▼ (SAFE)
发送给 Guest
```

## 2. 联邦记忆系统 (Phase 19)

### 2.1 物理存储隔离与加载机制
抛弃了旧版的单文件 `MEMORY.md` + 正则沙箱方案以及全员挂载 `USER.md` 的耦合方案。

#### A. 记忆文件架构 (Federated Memory)

| 文件类别 | 路径 | 加载 / 读写权限 |
|----------|------|-----------------|
| 全域主脑 | `memory/core/global.md` | Master / Guest 皆加载。仅 Master 触发巩固时可写。 |
| 客体专域 | `memory/guests/{user_id}.md` | 严密物理隔离。**Master 私聊时也加载专属的 `guests/{master_id}.md`** 作为隔离存放主人隐私偏好的收纳箱。 |
| 动态群组缓存 | `memory/core/groups.json` | 增量群名 ID 映射，跨会话读取 |

#### B. Bootstrap 核心潜意识注入 (Core Identity Prompt)
不再使用 `USER.md` 作为全局强推的主人档案。取而代之的是，系统在启动和每一次请求前，强绑定以下四大基石文件作为“出厂系统潜意识”：
- `SOUL.md`：核心心智模型（双面人、外交裁剪、群聊权力降级定律）。
- `AGENTS.md`：岗位职责与操作流（使用 cron 与越权工单的行政规范）。
- `HEARTBEAT.md`：30 分钟轮询心跳的私人工作簿（指示闲时去做记录整理）。
- `TOOLS.md`：职场操作安全红线。

**客体联系人别名提取 (Phase 25)**
客体专域不仅用于隔离与信誉模型，还作为本地联系人搜索的降级数据源：通过将外号等信息记录为 `Alias: xxx`，SearchContactsTool 工具将会自动扫描并命中真实 `user_id`，以辅助无法按名字搜索的钉钉接口。

### 2.2 YAML Frontmatter 信誉模型
每个 Guest 文件头部包含量化的社会模型参数：
```yaml
---
trust_score: 50
---
```
信誉分由潜意识反思引擎根据交叉验证结果自动调整。

### 2.3 核心类 `MemoryStore` (`agent/memory.py`)
- `read_global()` / `write_global()` — 全域记忆读写
- `load_groups()` / `save_group_info()` — 动态群组信息缓存读写 (Phase 25)
- `read_guest(user_id)` / `write_guest(user_id, content)` — 客体记忆读写（含 YAML 解析）
- `get_memory_context(is_master, current_user_id)` — Master 获取全集；Guest 获取 global + 本人专域
- `consolidate(session, provider, model, is_master, current_user_id)` — 记忆巩固，分别写入 guest/global

## 3. 潜意识反思引擎 (Phase 20)

### 3.1 `ReflectionAgent` (`agent/reflection.py`)
独立的后台 Agent，无对外通信接口，仅通过事件触发。

**触发时机**：Guest 完成一次对话并成功巩固记忆后，`loop.py` 的 `_consolidate_memory` 方法会异步创建反思任务。

**工作流程**：
1. 加载 Guest 记忆 + Global 记忆
2. 构造批判性分析 Prompt，交叉比对
3. 调用 `save_reflection` 工具：
   - `trust_score_adjustment`: 信誉分增减
   - `guest_memory_update`: 更新 Guest 文件（追加标签如 `[Caution/Rumor]`）
   - `global_knowledge_update`: 高可信度情报反哺全域
   - `alert_to_master`: 危险预警推送至 Master 钉钉频道

## 4. 三态安审防火墙 (Phase 17)

### 4.1 `SanitizerAgent` (`agent/sanitizer.py`)
独立于 Core Agent 的轻量安审模型，在主脑推理**之前**运行。

**Input Sanitizer — 三态分类**：
| 判定 | 行为 |
|------|------|
| `SAFE` | 放行至 Core Agent |
| `BLOCK` | 直接返回外交拒绝辞令，不触发主脑 |
| `ESCALATE` | 创建异步工单 → 转发 Master → 安抚 Guest |

**Output Auditor**：Core Agent 生成回复后，在发送前进行最终脱敏审查。检测到泄露（TrustScore、架构代码、内部标签等）时强制重写。

**关键实现细节**：使用 `_strip_think()` 方法清洗 LLM 返回中的 `<think>` 推理标签，避免思维链内容被误判或泄露。

## 5. 异步工单安抚系统 (Phase 18)

### 5.1 `TicketManager` (`agent/tickets.py`)
JSON 持久化的工单池，存储于 `memory/tickets/active_tickets.json`。

- `create_ticket(guest_id, channel, chat_id, content)` → 生成 `TKT-XXXXXXXX`
- `resolve_ticket(ticket_id)` → 闭环并移除
- `get_stalled_tickets(timeout_minutes)` → 返回超时未处理工单
- `mark_pacified(ticket_id)` → 标记已安抚

### 5.2 工具链
- `EscalateToMasterTool`：大模型调用 → 创建工单 → 转发 Master → 返回安抚句
- `ResolveTicketTool`：Master 决断后 → 关闭工单 → 推送回复给 Guest

### 5.3 后台安抚心跳 (`loop.py: _run_pacifier_cron`)
每 60 秒扫描工单池，超过 30 分钟未批复的工单自动生成高情商安抚话术推送给等待中的 Guest。

## 6. 职能行为手册 (Phase 16)

### 6.1 Guest Mode Prompt (`agent/context.py`)
在 `_get_identity` 中注入五维行为守则：
1. **信息收集**：主动提取访客姓名、公司、来意、联系方式
2. **模糊挡驾**：永不透露老板精确日程，以泛化口径回答
3. **SOP 路由**：关键词匹配 → `read_file` 读取 `sop/` 目录文档
4. **升级规则**：超出职权 → `escalate_to_master`
5. **隐私防火墙**：禁止透露其他 Guest 信息和内部架构

## 7. 身份路由层 (Phase 15)

### 7.1 配置 (`config.json`)
```json
{ "channels": { "dingtalk": { "master_ids": ["014224562537153949"] } } }
```

### 7.2 身份判定 (`loop.py: _process_message`)
在消息处理最早期计算 `is_master = msg.sender_id in master_ids`，贯穿后续所有环节。

## 8. 数据安全红线
1. Guest 对话时绝不挂载其他 Guest 的物理文件路径
2. 所有外发消息必须经 Output Auditor 脱敏审查
3. `<think>` 标签必须在所有 Sanitizer 响应解析前清洗
4. Master 拥有绝对穿透权限，不受任何安审网关拦截
