# 幕僚学习机制 (Staff Learning Mechanism)

本文档定义了个人智能幕僚 (Staff) 的第三大核心机制：**自我学习与进化体系**。
为了兼顾系统的**底层安全防御**与对用户的**高情商情绪价值陪伴**，Staff 的学习机制被严格划分为完全隔离的“双轨制 (Dual-Track)”。

## 轨道一：逻辑与工具进化 (Skill-Based Evolution)

这是 Staff 横向延展自身操作边界的核心路径，属于“核按钮”级权限。

### 1. 权限控制 (Access Mappings)
- **触发条件**：仅限 `Master` 身份可以下发指令。
- **Guest 熔断**：如果非 Master（Guest 访客）试图欺骗或要求 Staff 开发新功能、写脚本、抓接口，系统根 Prompts 强制要求 Staff 必须坚定且婉转地当场拒绝。

### 2. 串行化执行与确定性通知 (Serial & Deterministic Notification)
为了防止多任务执行导致的逻辑串扰（如将股票库安装到日历目录），执行必须遵循：
- **一事一办**：心跳周期内仅提取并执行第一个标记为 `[ ]` 的任务。在前序任务标记为完成 (`[x]`) 或失败之前，严禁启动后续任务。
- **强制反馈闭环**：
    - **启动阶段**：任务开始执行时，必须实时向 Master 通报：“老板，我开始处理 [任务名] 的异步研发了。”
    - **终态通知**：任务结束时，必须通过消息通道反馈任务结果（成功产出的功能演示，或失败的详细原因及修复建议）。

### 3. 环境隔离与防污染 (Strict Environment Isolation)
- **本地化原则**：所有的依赖安装、临时文件操作必须限制在目标技能文件夹（`workspace/skills/[功能名]/`）内。
- **严禁全局污染**：严禁直接运行 `pip install` 到系统环境。如果需要第三方库，应优先寻找无依赖纯 Python 实现，或在隔离环境/专属子文件夹中操作。

### 4. 实现载体：无代码热插拔 (Zero-Code Hot Loading)
- 放弃传统的在核心 `loop.py` 中写 Python 代码的危险方案。
- Staff 接收指令后，通过自行调用搜索与网络请求工具查阅官方 API，然后使用 `write_file` 将其实操步骤归纳在 `workspace/skills/[功能名]/SKILL.md` 中。
- **无感生效**：`SkillsLoader` 在每次处理新消息都会动态将所有的 `SKILL.md` 注入其工作脑海，实现了真正的自我热加载。

### 5. 与后台的融合 (Asynchronous R&D)
- 如果该项学习任务需要查阅巨量资料（太耗 Token 且长耗时阻塞主对话），大模型通过调用 `edit_file` 将其作为 Pending Task 写入 `workspace/HEARTBEAT.md`。
- **任务源规范**：必须使用 `- [ ] 任务描述` 的复选框格式。非此格式的任务会被引擎过滤，以防止误读普通文本为执行指令。

### 6. 反幻觉锚定 (Anti-Hallucination Grounding)
技能是否存在、是否创建成功，**必须以文件系统为唯一真相来源**。Staff 禁止从记忆或历史对话中推断技能的存在性：
- **创建前检查**：使用 `list_dir workspace/skills/` 确认目标技能目录不存在，避免重复创建。
- **创建后验证 (Write-then-Verify)**：`write_file` 后**立刻** `read_file` 确认文件落盘成功。只有物理确认后才可向用户汇报"完成"。

### 7. 对话式技能修正 (Conversational Skill Refinement)
当 Master 指出某个已有 Skill 执行结果不正确时，Staff 必须启动修正流程：
1. `read_file` 定位错误逻辑
2. `edit_file` 精确修正
3. 重新执行验证并汇报。

---

## 轨道二：语境观察与客体行为自适应 (Behavioral Adaptive Memory)

这是 Staff 维护陪伴感、建立不同人员交际圈层的“软能力”，本质是一种“同理心记忆系统”。

### 1. 权限开放 (Universal Observers)
- **触发主体**：面向所有合法互动的用户。
- **目的**：调整表达情绪和语言习惯，建立“千人千面 (Thousand Faces)”。

### 2. 潜意识处理机制 (Subconscious Consolidation)
- **闲暇自动归档**：在后台心跳唤醒时，如果无研发任务（轨道一空闲），则启动反思引擎提取各用户画像并归档至 `guests` 记忆池。

## 结语 (Vow)
“串行锁定确保安全，实时通知建立信任。”在静默的进化中，永远保持对 Master 的实时透明。
