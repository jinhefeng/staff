# 智能体级定时任务：前置校验与裁决架构 (Autonomous Validated Cron Architecture)

在传统的 Chatbot 或 Agent 框架中，定时任务（Cron）通常被实现为一个“定时发送消息留言板”。一旦任务被设定，系统会无脑进入死循环，直到被人工通过特定命令（如 `remove_job`）强行打断。这种传统设计存在两大致命缺陷：
1. **死循环滥发**：如果用户已经做出了响应，但系统尚未人工干预，大模型只会一次次无情地发送同一句催促。
2. **能力脱节（幻觉任务）**：大模型可能会设定一个“每十分钟查一次邮件，如果收到录取通知就停止”的任务。但实际上底层系统当前根本没有挂接读取邮件的 Tool。大模型设定任务时沾沾自喜，醒来执行时才发现手无寸铁，导致任务崩溃或直接卡死。

为彻底解决这些痛点，Staff 系统引入了业界领先的**“前置武器库校验机制 (Pre-flight Tools Validation)”**与**“唤醒即审判架构 (Arbitration Runtime)”**。

---

## 核心设计理念

**“不要在战场上才去清点弹药，也不要在盲目开火后才去确认死亡。”**

大模型在生成长期自动化任务时，系统不再无条件接纳。它必须经历一个严苛的全生命周期管控：**制定计划 -> 能力自检 (Pre-flight) -> 落地挂载 -> 唤醒审判 (Arbitration) -> 处决执行**。

---

## 架构三要素 (The 3-Tier Structure)

我们将原本单一的 `message` 字段，解构为逻辑严密的“三段式协议”。在调用 `cron` 工具的那一刻，系统强制要求大模型提供以下三个变量：

1. **执行内容 (`task_content`)**
   - 任务醒来后真正要去执行的动作（例如：`"发送一条催缴日报的微信给员工X"`）。
2. **终止条件 (`stop_condition`)**
   - 一段高度语义化的纯自然语言描述（例如：`"检查员工X是否在最近10分钟回复了消息或提交了文档"`）。
3. **武器清单 (`required_tools`)**
   - 大模型作为“规划者”，必须提前声明：“我未来醒来去评估上面的 `stop_condition` 时，我需要用到系统里的哪些具体工具？”（例如：`["read_recent_messages"]`）。

---

## 第一层屏障：前置武器库校验 (Pre-flight Validation)

这是**防止大模型幻觉**的绝对护城河。

### 运行机制
当大模型试图提交一个 Cron Job 申请时：
1. 底层拦截器（`CronTool._add_job`）启动。
2. 引擎会拉取当前 AgentLoop 中**已实际挂载**的所有可用工具名录（可用技能树）。
3. 将大模型提交的 `required_tools` 与系统实际清单做严格的并在运算（求交集）。

### 物理拦截逻辑
如果出现哪怕一个无法匹配的缺失工具，系统会立刻 **阻断创建动作**，并将致命错误拍回到大模型的上下文中，迫使它重新思考：

> `Error: PRE-FLIGHT VALIDATION FAILED! You requested tools that are not currently mounted in the system: ['read_wechat', 'check_email']. You do NOT have the capability to independently evaluate your stop condition or execute this task. Please adjust your plan, remove the dependency on these tools, or ask the user to mount the corresponding plugins first.`

**意义**：这一步逼得大模型只能制定*“它确实有能力独立完成并在指定条件闭环”*的计划。

---

## 第二层屏障：解耦式的唤醒即审判架构 (Two-Phase Arbitration & Execution Runtime)

当系统时间轮（Time Wheel）转动到触发点时，系统绝不直接执行发信（`task_content`）。为了防止大模型在**“评估意图”**与**“生成发信文案”**之间产生精神分裂（即身份混淆或标签泄露），整个执行流被强行解耦为两次完全独立的 LLM 调用。

### Phase 1: 绝对封闭的裁判所 (Arbitration)
底层 Python 引擎首先包装一段强指令 Prompt，以**系统造物主**的角色发起第一次调用。
这个阶段没有 `task_content`，只有 `stop_condition` 的严格拷问：

```text
【System Timer Triggered: Arbitration Phase】
**Stop Condition check required:**
You previously defined this semantic stop condition: "员工是否已经提交了文件"

INSTRUCTION:
1. Use your available tools (which you pre-claimed: ['read_recent_messages']) to verify if this condition is currently met.
2. CRITICAL MATCHING RULE: You must be STRICT. Only output `[ACTION: STOP]` if the condition is explicitly and clearly met in the retrieved context. Do NOT guess or assume it is met. If the target string or intent is NOT found, it is NOT MET.
3. If the condition IS MET (or you should stop the cycle), you MUST output exactly `[ACTION: STOP]` and nothing else.
4. If the condition IS NOT MET, you MUST output exactly `[ACTION: CONTINUE]` and nothing else.
CRITICAL: Do NOT execute the actual task in this step!
```

**拦截结算**：
- 如果大模型输出 `[ACTION: STOP]`，底层立即执行 `cron.remove_job()` 并截断流程。整个任务如幽灵般悄然寂灭。
- 只有输出 `[ACTION: CONTINUE]`，才会被允许进入下一阶段。

### Phase 2: 纯净的执行器 (Execution)
在 Phase 1 给出放行许可后，底座发起第二次、也是最纯净的指令调用。
此时，大模型重新戴上体贴助理的“Staff面具”，Prompt 里面没有任何复杂的规则束缚：

```text
【System Task Execution】
Please execute the following scheduled task immediately:
Task Content: "催缴日报"
INSTRUCTION: Act immediately! Notify the user in a friendly manner or perform the task directly...
```

**意义**：在这独立的一环，模型无需思考是否需要输出状态标记，它只需专注地扮演助理完成动作，确保生成的文本 100% 自然纯净，直接通过底层信道外发给最终受众。

### 特权通道：系统级指令的安全审查豁免 (Sanitizer Bypass)
为了确保 Phase 1 与 Phase 2 的内部指令不被外部对话防护策略（Sanitizer）误杀（例如因包含 "INSTRUCTION", "CRITICAL" 等强制词汇被当成 Prompt Injection 拦截），系统引入了 **信任透传标记 (`is_system_internal=True`)**。
- 由系统主动发起的进程（如 Cron、Heartbeat）在调用 `process_direct` 时，强制携带该标记。
- 消息处理总线 (`_process_message`) 识别到该标记后，主动跳过输入净化步骤，保障系统任务无阻碍执行。

---

## 架构演进与衍生价值

1. **泛用型上帝视角守护**
   有了这个架构，Cron 不再是“定时发消息服务”，而是一个真正的“挂起进程”。诸如：“每周周五去搜一下网页看本周发了什么新AI模型，如果有就推给我，如果没有就停止本周轮询”这种高阶需求，只需大模型组合 `['web_search']` 工具即可无写代码接入。
2. **倒逼原子工具层开发**
   系统的 Pre-flight Validation 就是一个指路明灯。当大模型多次试图建构某种监控任务却屡屡因“技能缺失”被拦截时，这意味着我们迫切需要为其编写新的底层原子工具（如 `ReadRecentMessagesTool` 就是被此架构逼迫出的衍生基础设施）。
