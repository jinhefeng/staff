# 实时监控系统交互说明书 (Monitor System Interaction Spec)

## 1. 视觉风格 (Visual Identity)
- **主题**：暗黑科技感 (Cyberpunk / Modern Dark)。
- **色调**：
  - 背景：`#0f172a` (Deep Space Blue)。
  - 强调色：`#38bdf8` (Sky Blue) & `#818cf8` (Indigo)。
  - 成功/完成：`#10b981` (Emerald)。
  - 待办/处理：`#f59e0b` (Amber)。
- **字体**：`Poppins`, `Inter`, 或系统默认无衬线字体。

## 2. 布局设计 (Layout)
- **Header**：左侧为“Staff Monitor”标题，右侧为服务器状态及数据更新倒计时。
- **Main**：
  - **Top Row**：四个指标卡片（总工单、待执行任务、活跃对话、系统心跳状态）。
  - **Middle Row (Left 2/3)**：工单详细列表，支持溢出滚动。
  - **Middle Row (Right 1/3)**：Heartbeat 任务清单，Checkbox 风格。
  - **Bottom Row**：会话活动日志摘要。

## 3. 交互流程 (Interactive Flow)
- **自动刷新**：页面加载后开启每 60 秒一次的自动 Fetch 请求。
- **指标闪烁**：当有新工单产生时，工单数指标卡片会有微弱的呼吸灯效果。
- **工单交互**：点击工单行，展开显示完整内容。
- **响应式排版**：支持移动端单列显示。

## 4. 微动画 (Micro-animations)
- 使用 CSS Transitions 实现平滑的颜色切换和列表项淡入。
- 数据刷新时增加顶进度条提示。
