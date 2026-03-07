# 任务管理强制准则 (Task Management Mandatory Rules)

## 核心原则
- **禁止精简历史**：`.agents/docs/task.md` 是项目的工作路线图。严禁删除、聚合、隐藏或精简任何已标记为 `[x]` (已完成) 或 `[Needs Review]` 的任务阶段。
- **追加模式 (Append-Only)**：对任务列表的修改必须以追加 (Append) 或状态更新 (Status Update) 为主。任何删除操作必须得到用户的显式许可。
- **层级持久化**：所有的阶段 (Phase) 编号必须保持连续，不得重置或大幅度重构历史编号。

## 执行检查清单
1. 在调用 `write_to_file` 或 `replace_file_content` 修改 `task.md` 前，必须确认旧的已完成阶段依然存在。
2. 任何“为了简洁”而进行的精简都是错误的。
