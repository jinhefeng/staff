# 功能说明书：记忆专家技能 (staff-memory-expert)

## 1. 业务背景与动机
随着 Staff 系统的运行，聊天历史与记忆文档逐渐膨胀，导致 LLM 上下文（Context）负载过重，Token 成本上升且响应速度变慢。原有的物理裁剪逻辑（180->40）虽能控制 Context，但会导致原始对话细节永久丢失。

## 2. 核心架构设计 (The Shadow-Skill Architecture)
系统引入了“影子日志”与“技能解耦”双轨架构：

### 2.1 影子日志 (Shadow Log)
- **位置**：`workspace/sessions/raw_history/{chat_id}.jsonl`
- **逻辑**：在 `loop.py` 层面实现追加式记录。所有 User/Assistant/Tool 消息在进入 Session 前会被物理备份。
- **特性**：只增不删，不受物理裁剪影响，作为全量情节记忆的“底片”。

### 2.2 记忆专家技能 (The Skill)
- **定位**：Staff 的内省中心，管理全量检索与知识提纯。
- **解耦点**：将 `MemoryStore.consolidate` (Map-Reduce) 从核心库移出，封装为技能工具。

## 3. 工具箱定义 (Tooling)
- `search_chat_history`: 基于 `raw_history` 的全文检索工具。
- `query_global_knowledge`: 对 `global.md` 进行按需检索（RAG）。
- `read_full_profile`: 读取访客 MD 画像全文。
- `consolidate_memory`: 执行归档提纯逻辑（由内核异步触发）。

## 4. RAG 化上下文加载
- **ContextBuilder 优化**：停止向 System Prompt 注入 `global.md` 和 `guest.md` 的 Body。
- **索引模式**：仅注入 Identity YAML 标头。LLM 必须通过工具获取详情。

## 5. 权限与安全
- **隔离原则**：Guest 模式检索工具受 `user_id` 过滤，严禁跨 Session 搜索。
- **Master 穿透**：Master 具备全域检索权限。
