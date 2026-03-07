# 实时监控系统功能说明书 (Monitor System Functional Spec)

## 1. 业务逻辑描述
实时监控系统旨在为用户提供对 `Staff` 运行状态的直观视图，减少用户通过文件阅读来确认进度的负担。

### 核心功能模块：
1. **工单看板 (Ticket Dashboard)**：
   - 提取自 `workspace/tickets/active_tickets.json`。
   - 显示总活跃工单数。
   - 列表展示工单 ID、发起人、内容摘要及创建时间。
2. **Heartbeat 状态 (Heartbeat Monitor)**：
   - 提取自 `workspace/HEARTBEAT.md`。
   - 解析 `Active Tasks` 列表，展示待办事项及其状态（已完成/待办）。
3. **对话流监控 (Session Monitor)**：
   - 扫描 `workspace/sessions/` 目录。
   - 展示最近活跃的对话记录（源文件、最后更新时间、消息条数）。
4. **后台任务流 (Background Tasks)**：
   - 识别工单内容中包含 `[DEFERRED TASK]` 的条目，单独汇总展示。

## 2. API 定义 (Data Structure)
系统采用“文件静态化”方案，由后台脚本生成 `data.json` 给前端使用。

**data.json 结构示例**：
```json
{
  "last_updated": "2024-03-07T23:30:00Z",
  "tickets": {
    "total_active": 10,
    "items": [...]
  },
  "heartbeat": {
    "tasks": [
      {"text": "任务内容", "status": "pending/completed"}
    ]
  },
  "sessions": {
    "active_count": 5,
    "recent": [...]
  }
}
```

## 3. 边缘案例处理
- **数据延迟**：前端增加最后更新时间的强制显示，告知用户数据的新鲜度。
- **文件锁定**：读取 `json` 时使用只读模式，避免干扰 `nanobot` 写入。
- **空状态**：当没有工单或待办时，显示精致的 Placeholder 动画。
