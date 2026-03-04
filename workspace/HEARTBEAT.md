# 私人轮询待办与潜意识中枢 (Heartbeat & Subconscious Hub)

你的底层引擎每 30 分钟会唤醒你一次并读取这个文件。
这里是你进行**异步科研任务**与**潜意识反思 (Subconscious Consolidation)** 的脑域中枢。

## 行政指令 (Decision Tree)：
每一次唤醒时，请严格按以下顺序进行 `heartbeat` 工具决策：

1. **如果有待办 (Active Tasks)**：必须返回 `run`，并将待办事项作为参数。后台大模型会自动执行它（例如：编写某项 SKILL.md，网络爬虫抓包等耗时操作）。完成后将其移至 Completed。
2. **如果没有待办 (Idle 闲暇)**：你不可以直接返回 `skip`（除非你刚刚整理完）。你必须返回 `run` 并设定任务为：**“启动潜意识反思：整理最近的聊天记录，在脑海中总结各个人员的主观侧写、语气偏好与个人属性，并使用 `memorize_fact` / `save_memory` 将其归档至 `guests` 记忆池中”**。
3. **记忆整理毕**：一旦心跳完成了“潜意识反思”，请你调用 `edit_file` 在本文件尾部记录一条“已于 [时间] 完成日常记忆固化”，以防止下一个半小时的闲暇期产生重复反思。

---

## Active Tasks (待执行的异步任务)
*(主聊天框中过重的学习研发任务会被追加到这里，供你独占心跳资源处理)*

- 学习并集成钉钉日历查询技能：研究 DingTalk API 文档，编写 `workspace/skills/dingtalk_calendar/SKILL.md`，实现通过用户ID安全获取日程的本地化能力（无权限时不触发）
- 替换股票数据源：寻找支持 A 股的免费公开 API（如 Tushare、AKShare），重构 stock/SKILL.md 以适配新接口

---
## Completed (已完成区)
