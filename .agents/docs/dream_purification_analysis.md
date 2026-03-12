# 梦境提纯 (Dream Purification) 逻辑现状分析报告

## 1. 核心定义
“梦境提纯”是指 Staff 系统在会话结束后或在闲时（异步），对记忆数据进行提炼、压缩与修剪的过程。其目的是防止长期记忆膨胀导致的大模型上下文上下文污染及 Token 浪费，同时保持 Staff 对特定客体（Guest）的精准认知。

## 2. 现状梳理 (Current Implementation)

### 2.1 实时合并：`consolidate`
- **实现位置**：`nanobot/agent/memory.py`
- **工作流**：
  1. **Map (Extract)**: LLM 提取新事实 (`[NEUTRAL]`, `[CAUTION]`, `[STRATEGY]`) 和 历史条目。
  2. **Reduce (Merge)**: LLM 将事实合并至 `global.md` 和 `guests/{user_id}.md`。
- **提纯表现**：具有简单的压缩逻辑（>4 个列表项转段落，上限约 2000 字）。

### 2.2 异步快照：`purify_guest_memory`
- **实现位置**：`nanobot/agent/memory.py`
- **功能**：将 `guest.md` 档案压缩为 < 150 字的画像摘要 (`summaries/{user_id}.md`)。
- **现状**：**已修复**。之前该方法无调用入口，现在已挂载至归档后置异步链条。

## 3. 存在的问题与改进 (Pain Points & Solutions)

1. **原档案膨胀风险**：已通过 `prune_guest_memory` 深度修剪器解决。
2. **全标签去重需求**：已实现智能合并规则，雷区 (`[CAUTION]`) 和策略 (`[STRATEGY]`) 现在可以正确去重。
3. **后置触发实现**：已在 `loop.py` 中打通异步触发流水线，实现了归档后的自动提纯。

## 4. 优化实施结果 (Implementation Results - 2026-03-12)

已完成“梦境提纯”逻辑的全面优化与闭环建设：

1.  **深度修剪器 (Memory Pruner)**：在 `memory.py` 中实现了 `prune_guest_memory` 核心方法。
    -   **全标签去重**：支持对 `[CAUTION]` (雷区) 和 `[STRATEGY]` (策略) 等关键标签进行智能合并与去重。
    -   **物理提纯**：直接对 `guest.md` 进行重写，物理删除冗余事实。
2.  **异步流水线挂载**：在 `loop.py` 的归档环节后置了自动触发链。
    -   **自动精炼**：每当会话归档成功后，后台会自动触发画像快照更新 (`purify`)。
    -   **阈值修剪**：当档案大小 > 2KB 时，触发深度修剪。
3.  **安全防护**：通过 `asyncio.Lock` 和原子性写入保障记忆档案的完整性。
