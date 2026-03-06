# Heartbeat 与梦境提纯消息机制说明 

## 背景
HeartbeatService 会定期唤醒 AI 幕僚检查后台工单（任务）或在闲暇时执行“梦境提纯”（潜意识反思，Subconscious Reflection）。

## 消息通知机制优化
为减少对用户的打扰，同时保证系统运行透明度，针对“梦境提纯”任务的通知机制做如下规定：
1. **梦境提纯开始时**：不再发送启始通知消息。系统在后台默默启动记忆处理过程。
2. **梦境提纯结束时**：完结时需发送消息，且包含提纯结果。将模型提纯的实际结果摘要作为汇报内容，直接呈现给用户（Master），使其知道提纯正在正确运行。
3. **普通异步工单任务**：保持原有的“开始启动”与“最终完结汇报”的双重通知逻辑不变。

## 存储治理 (Storage Governance)
为防止周期性任务产生大量 Token 冗余及存储损耗，系统强制执行以下隔离：
1. **差异化裁剪**：后台任务会话固定使用 `BackgroundMaxMessages` (100) 阈值，并在裁剪时仅保留 `ClearToSize` (50) 条，以维持“最近经验优先”的上下文。
2. **物理文件回收**：任何超过 15 天未更新的旧版 Cron/Heartbeat 日志文件将被物理删除，详情参见 [Session 管理规范](file:///Users/jinhefeng/Dev/staff/.agents/docs/session_management_spec.md)。
