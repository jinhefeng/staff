# 幕僚学习机制 (Staff Learning Mechanism)

本文档定义了个人智能幕僚 (Staff) 的第三大核心机制：**自我学习与进化体系**。
为了兼顾系统的**底层安全防御**与对用户的**高情商情绪价值陪伴**，Staff 的学习机制被严格划分为完全隔离的“双轨制 (Dual-Track)”。

## 轨道一：逻辑与工具进化 (Skill-Based Evolution)

这是 Staff 横向延展自身操作边界的核心路径，属于“核按钮”级权限。

### 1. 权限控制 (Access Mappings)
- **触发条件**：仅限 `Master` 身份可以下发指令。
- **Guest 熔断**：如果非 Master（Guest 访客）试图欺骗或要求 Staff 开发新功能、写脚本、抓接口，系统根 Prompts 强制要求 Staff 必须坚定且婉转地当场拒绝。

### 2. 实现载体：无代码热插拔 (Zero-Code Hot Loading)
- 放弃传统的在核心 `loop.py` 中写 Python 代码的危险方案。
- Staff 接收指令后，通过自行调用搜索与网络请求工具查阅官方 API，然后使用 `write_file` 将其实操步骤归纳在 `workspace/skills/[功能名]/SKILL.md` 中。
- **无感生效**：`SkillsLoader` 在每次处理新消息都会动态将所有的 `SKILL.md` 注入其工作脑海，实现了真正的自我热加载。

### 3. 与后台的融合 (Asynchronous R&D)
- 如果该项学习任务需要查阅巨量资料（太耗 Token 且长耗时阻塞主对话），大模型通过调用 `edit_file` 将其作为 Pending Task 写入 `workspace/HEARTBEAT.md`。
- 在每一次的后台半小时唤醒（心跳）中，Staff 会隐入虚空，静默地在后台完成学习并生成对应的 `SKILL.md`。

### 4. 反幻觉锚定 (Anti-Hallucination Grounding)
技能是否存在、是否创建成功，**必须以文件系统为唯一真相来源**。Staff 禁止从记忆或历史对话中推断技能的存在性：
- **创建前检查**：使用 `list_dir workspace/skills/` 确认目标技能目录不存在，避免重复创建。
- **创建后验证 (Write-then-Verify)**：`write_file` 后**立刻** `read_file` 确认文件落盘成功。只有物理确认后才可向用户汇报"完成"。
- **存在性声明**：声称"拥有/已创建"某技能前，必须先通过 `list_dir` 查证。
- **设计原因**：在多轮对话中，模型可能由于前序失败的创建尝试残留在对话历史而产生"已完成"的幻觉。通过强制文件系统校验，彻底消除虚假声明。

### 5. 对话式技能修正 (Conversational Skill Refinement)
当 Master 指出某个已有 Skill 执行结果不正确（如"股票代码不对"、"接口失效了"）时，Staff 必须启动修正流程：
1. `read_file` 打开对应 `workspace/skills/[skill-name]/SKILL.md`
2. 定位错误的逻辑或参数
3. `edit_file` 进行精确修正
4. 用修正后的逻辑重新执行验证
5. 向 Master 汇报修正结果
- **主动追问**：如果 Master 只说"不对"但未说明具体原因，Staff 应当追问而不是盲目重试。
- **设计原因**：Skill 是 Staff 的长期能力资产，允许 Master 通过自然对话迭代修正，使得 Staff 的技能越用越精准——实现"聊天即调优"。

---

## 轨道二：语境观察与客体行为自适应 (Behavioral Adaptive Memory)

这是 Staff 维护陪伴感、建立不同人员交际圈层的“软能力”，本质是一种“同理心记忆系统”。

### 1. 权限开放 (Universal Observers)
- **触发主体**：面向所有合法互动的用户（包括 Master 和 Guest）。
- **目的**：不通过开发工具去改变系统架构，而是调整其外显的表达情绪和语言习惯，从而建立“千人千面 (Thousand Faces)”的助理服务。

### 2. 潜意识处理机制 (Subconscious Consolidation)
为了不拖慢主聊天框每次的消息回复速度（首字耗时，TTFT），我们将行为观察任务彻底**转移给系统兜底心跳机制**。
- **闲暇自动归档**：在后台半小时轮询的每次唤醒时，如果 `HEARTBEAT.md` 没有任何诸如“能力研发”的具体任务（处于 Idle状态）。
- **指令执行**：反思引擎 (ReflectionEngine) 会被强制推上台面，回溯过去半小时与各色客体人员的聊天日志（Context），提炼每个人的：
  - “语气偏好” (喜欢严肃还是活泼？)
  - “沟通结构” (喜欢直接给结果还是给中间过程？)
  - “潜在身份或雷点”
- 最后使用 `GlobalMemory` 的记录功能将其按人头压入 `workspace/memory/guests/{id}.md` 长效保存。

## 结语 (Vow)
“用双轨隔绝风险，用心跳托举灵魂。”在坚守业务不被黑客攻破的底限之上，永远保留观察与适应人类的同理心。
