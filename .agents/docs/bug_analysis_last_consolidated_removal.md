# 冗余字段清理分析报告：last_consolidated 遗毒

## 1. 遗留字段现状分析 (As-Is)
经过全局检索检测，整数型旧字段 `last_consolidated` 虽然退出了主流的后台归档触发判定，但在目前的系统中依旧有 **7处参与读写**，并且其中一处存在极其危险的历史包袱级 Bug：

- **反序列化残余 (nanobot/session/manager.py)**：每次保存与读取 Session 时，依旧在往磁盘 JSONL 头写入此字段。
- **降级兼容的陷阱 (nanobot/session/manager.py)**：在组装 LLM 历史上下文 `get_history()` 的降级分支中使用了它。
- **致命的悬空指针Bug (nanobot/agent/loop.py: 750)**：在处理用户的 `/new` 强制归档指令时，竟然还在调用 `snapshot = session.messages[session.last_consolidated:]`。正如我们之前推论的，当消息总数因为达到 `90` 强行被物理斩首到 `40` 时，这个永远累加的 `96` 会直接超过数组长度，导致空切片、甚至报 `IndexError` 错觉！用户发出 `/new` 后，什么都不会被归档。

## 2. 根原因与潜在影响 (Root Cause & Impact)
- **幽灵索引 (Ghost Index)**：整数索引与物理斩首机制（`sessionMaxMessages` 和 `sessionClearToSize`）天生互斥。物理斩首会使得数组长度瞬移回退，而整数累加计数器继续向前，两者必然撕裂。
- **影响评估**：极高（High Risk）。只要此字段仍作为硬编码下角标截取数组，任何基于它的截取逻辑都会由于截断保护而产生灾难性失效。

## 3. 建议解决方案 (Proposed Solution)
对 `last_consolidated` 进行“连根拔起”式的彻底移除：
1. **Model 层剔除**：从 `nanobot/session/manager.py` 的 `Session` 数据类结构中彻底去掉 `last_consolidated` 定义，并从序列化 `_load()` 与 `save()` 中剔除它的存取代码，停止脏数据落盘。
2. **重构历史截取**：在 `get_history()` 中的 Legacy Fallback，改为安全的 `start_idx = 0`（把剩余的所有消息视作未归档，因为旧兼容已被修剪覆盖，不用担心爆炸）。
3. **修复 `/new` 死亡切片**：在 `loop.py` 执行 `/new` 逻辑时，改用同源的 **ID 锚点机制（last_consolidated_id）** 进行数组下标的实时穷举定位，再做切片。
4. **移除归档后累加**：在 `memory.py` 的 `consolidate()` 返回成功前，删除无意义的 `session.last_consolidated += len(...)`。
