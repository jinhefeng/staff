# Staff (个人智能幕僚) 开发任务大纲

## 阶段一：方案定义 (Definition Phase) [x]
- [x] 需求分析与架构设计确认
- [x] 编写《功能说明书》(functional_spec.md)
- [x] 编写《交互说明书》(interaction_spec.md)
- [x] 完善《总体架构文档》(architecture_spec.md)

## 阶段二：影响分析 (Impact Analysis) [x]
- [x] 梳理系统外部依赖 (微信机器人 Hook 等)
- [x] 数据流与状态流审查
- [x] 冲突发现与冗余检查
- [x] 输出《影响分析报告》(`impact_analysis.md`)
- [x] 方案选定：解析与定型系统核心编排引擎 (Round 1)
  - [x] 开源方案初筛（微信 Hook 模型与逻辑编排层对决）
  - [x] 确立逻辑编排引擎：对比 OpenClawd 与 NanoClawd 的架构适配度
    - [x] 接收并本地化存入 NanoClawd 源码
    - [x] 源码深度级（API 与工作流）解构与分析
    - [x] 【已废弃】输出《引擎选型最终建议及适配方案》
- [x] 方案重新选型：解析与定型支持多模型/Gemini的系统核心编排引擎 (Round 2)
  - [x] 确立逻辑编排引擎：遵照指令，最终选定极轻量级代理框架 `nanobot`
  - [x] 等待用户提供 `nanobot` 核心源码或 Github 仓库地址
  - [x] 源码深度级（多模型 API 兼容性与微信通道对接）解构与分析
  - [x] 输出基于 `nanobot` 的《引擎选型最终建议及落地实施方案》

## 阶段三：基于 nanobot 架构的扩展与同步 (Phase 3: Extension) [x]
- [x] 开发核心：微信接入通道 (WeChat Channel)
  - [x] 查阅 `nanobot` 原生 `BaseChannel` 类及加载注册机制
  - [x] 编写 `channels/wechat.py` 实现基于长轮询/事件挂载的 `WeChatFerry` 原生拦截器
  - [x] 抹平微信报文结构，输出与适配 `nanobot` 标准化的输入上下文引擎
- [x] 业务控制模块投递 (Staff Config & Skills)
  - [x] 修改 `nanobot` 群组及全局 Prompt，注入边界防越权能力规范
  - [x] 借助内建任务调度特性设计/预留了延时自动安抚逻辑架构
- [x] 启动联调与测试 (Final Integration)
  - [x] 将模型 Provider 切换至直连 Gemini (通过 `start.sh` 生成默认设配)
  - [x] 封装一键全流拉起脚本 `start.sh`
  - [ Needs Review ] 主人（您）在本地拉起服务，测试单聊/群聊下幕僚的反应链路

## 阶段四：不可抗力模型迁移与多网关并存 (Nvidia Provider Integration) [x]
- [x] 评估制定接入计划并等候确认 (保留双芯架构)
- [x] 源码层面植入 `nvidia` 为一等公民 Provider 注册表
- [x] 覆写并重构 `start.sh` 提供双端 API Keys 配置模板并指引 `minimaxai` 切换

## 阶段五：环境规范化与部署脚本拆卸 (Phase 5: Deployment) [x]
- [x] 架构重整：废除单文件强耦合启动。设计并编写纯净 `install.sh` 隔离构建 venv 虚拟环境及拉取依赖；编写轻量化 `start.sh` 专门司职守护运行与配置文件生成阻断机制。

## 阶段六：配置生态与交互体验优化 (Phase 6: DevEx) [x]
- [x] 架构重整：剥离全局配置体系。将 `config.json` 本地化绑定在工程根目录，提供 `config.sample.json` 模板文件并更新 `.gitignore` 黑名单；为两份启动脚本追加详实的步骤回显语料。

## 阶段七：跨平台容器化部署 (Phase 7: Cloud Native - BLOCKED) [x]
- [x] 彻底解耦 Windows 生态机制，放弃臃肿的 `WeChatFerry` 注入流架构路线，启动【方案 B：纯净 Gewechat 协议流】的重构。
  - [x] 编写跨平台极简 Dockerfile 封装 Nanobot 运行载体 (由于墙内基础设施全面被封禁导致构建报错)。
  - [x] 编写 `docker-compose.yml` 建立 nanobot 与官方 `gewechat` 大底座并存的双子星网络。
  - [x] 彻底移除旧代码的耦合，实现对 HTTP Hook 规范的新任通道 (`channels/gewechat.py`) 接管。

## 阶段八：半云原生混合架构回退 (Phase 8: Hybrid Native) [x]
- [x] 分解原定的纯双子星 Docker structure，改为 Gewechat 底座独立云化。
  - [x] 从 `docker-compose.yml` 中删去受阻的 Python `staff-bot` 业务节点，仅作微信登录凭证提供服务器用。
  - [x] 修复重构本地执行链 `install.sh`，剔除已删除死亡的 WeChatFerry 路径。
  - [x] 指南回退：打通本地宿主机端口网络，使从 `venv` 中启动的 Nanobot 能够通过 HTTP 与隔离箱里的 Gewechat 容器成功握手。

## 阶段九：独立模块解耦架构 (Phase 9: Decoupling Architecture) [x]
- [x] 架构剥离方案提交：明确微信作为**独立微服务网关**的边界。
- [x] 改造 `nanobot` 网关：不再关注并轮询验证底层通信服务的健康状态或强制管理其生命周期，仅作为事件驱动的通信接受者 (Webhook / HTTP Interface) 与之对接。

## 阶段十：全场景通信网关插座化 (Phase 10: Plug-and-Play Gateway) [x]
- [x] 插座与鉴权架构重设计：仿照大模型 Providers 逻辑设计多终端与微信多开群控架构，更新实现方案并恳求授权。
- [x] 改造 `nanobot/config/schema` 将原先的信道布尔配置扩充为包含 token 与 instance url 甚至 appId 的阵列映射表。
- [x] 改造 `GewechatChannel` 等系统信道层，支持从插座阵列中反向实例化并注册独立的 Webhook 事件处理器。

## 阶段十一：网关回调挂载与权证互信 (Phase 11: Webhook & Authorization) [x]
- [x] API 鉴权双向挂载实施方案提交：明确业务侧如何自动化接管大底座的事件推送。
- [x] 改造 `nanobot` API 核心路由，对外暴露统一的 `/{instance_name}/webhook` 入站接口接收不同端点的微信事件。

## 阶段十二：终端点火与扫码准入 (Phase 12: Terminal QR Login) [x]
- [x] 编写并提审终端扫码点火架构方案，确保符合用户“沉浸式控制台扫码”的预期。
- [x] 开发微信扫码鉴权 SDK 层（封装 Gewechat 的 `getLoginQrCode` 和 `checkLogin` 接口）。
- [x] 改造 `nanobot` CLI 命令集，新增 `nanobot channels login --channel gewechat --instance {name}` 指令以发起控制台二维码打印并轮询扫码结果。
- [x] 实现登录成功后的自动配置回填：将生成的 `app_id` 回写至 `config.json` 释放用户的心智负担。

## 阶段十三：异地解耦部署与穿透联调 (Phase 13: Distributed Deployment) - [ABANDONED] [x]
由于底座环境的不确定性，用户已放弃基于 Gewechat 的方案。
- [x] 清理代码资产：从系统内核中彻底拔除 `GewechatChannel`、配置表残留映射及关联 CLI 指令，保证系统纯净无冗余。

## 阶段十四：钉钉企业机器人原生对接 (Phase 14: DingTalk Native Integration) [x]
- [x] 申请：在钉钉开发者后台拉起企业内部机器人应用，并取得 `clientId` 和 `clientSecret`。
- [x] 联调：通过本地开发机运行的 webhook (18790) 配置进入钉钉开发后台的消息订阅/Stream 模式。
- [x] 配置：修改 `config.json`，停用微信并启用钉钉代理。

## 阶段十五：带权限标签的高阶混合记忆池 (Phase 15: Tag-based Shared Memory) [x]
- [x] 架构设计：重制原生的双层文本记忆，引入 [PUBLIC], [PRIVATE:uuid], [MUST-KNOW] 等知识元结构标签。
- [x] 动态上下文洗牌机制：开发 `get_filtered_memory` 函数。
  - [x] 主人视角透视：不受限读取全部记忆。
  - [x] 访客隔离洗牌：拦截剥离属于其他用户的私密记忆，只放行 [PUBLIC] 和有关本人的条目，防止串供与嚼舌根。
- [x] 开发主副人格 Prompt 引擎：
  - [x] 主人模式：绝对服从、精简回答、执行复杂指令。
  - [x] 访客与安防模式：通过高压指令禁止越权修改标签或刺探其他人隐私。

## 阶段十六：职能白名单与 RAG 引导 (Phase 16: White List & SOP) [x]
- [x] 信息收集：结构化提取访客意图与联系人信息。
- [x] 状态模糊查询：拦截窥探主人的精确日程，提供“正在开会”等模糊化状态。
- [x] SOP 流程引导：为特定词汇（如立项、报销）返回 RAG 标准指南。

## 阶段十七：安全审计与 Prompt 净化层 (Phase 17: Sanitizer & Audit) [x]
- [x] 防注入屏障层：在访客模式下前置丢弃/改写涉及“忽略之前指令、查看数据库”等攻击意图。
- [x] 脱敏输出审查：对即将发给外部访客内容的二次校验，防止泄露私密决策权。

## 阶段十八：异步跟进工单与超时安抚 (Phase 18: Asynchronous Auto-Pacifier) [x]
- [x] 异步等待环闭环逻辑：阅读、生成提案 -> 转发给主人 -> 等待批示 -> 实际对外回复。
- [x] 超时触发器：编写 cron/heartbeat 钩子，监控长时间未决议事项。
- [x] 安抚文案生成：超时发生时，主动向访客发送“事已加急，老板暂未脱身”等关怀话术。

## 阶段十九：联邦记忆系统与物理隔离 (Phase 19: Federated Memory Isolation) [x]
- [x] 将原先的统一单点 `MEMORY.md` 切分为网状分布式文件结构。
  - 主脑全域：`memory/core/global.md`
  - 客体专域：`memory/guests/{id}.md`
- [x] 对所有的 `ContextBuilder` 进行底层路径劫持替换，确保 Guest 面对 LLM 时绝不可能通过文件系统访问其他人员档案。
- [x] 在客体记忆头部建立量化的 YAML 标签标头，初始化包含信任度 `TrustScore: 50`。

## 阶段二十：潜意识反思网关 (Phase 20: Subconscious Reflection Gateway) [x]
- [x] 创建一个内部隐藏运转的独立 `Reflection Agent`（无对外通信接口，只靠 Cron 或事件触发）。
- [x] 开发反思推盘流水线：在每日闲时将不同客体的独立存档碎片与主全域记忆进行交叉比对。
- [x] 赋予最高批判性智力：根据 `TrustScore` 和比对矛盾度，自动化增减 Guest 的信用评分，将证实信息逆向反哺入全域知识库 `global.md`，并将危险风义预警主动推送给主理人审阅。

## 阶段二十一：工程架构提纯与扁平化 (Phase 21: Project Refinement) [x]
- [x] 核心代码提升：将 `nanobot` 提升至根目录。
- [x] 冗余清理：删除 `src`、`vendor` 等无效层级目录。
- [x] 自动化适配：更新 `install.sh` 与 `start.sh` 的路径依赖。
- [x] 语法与启动校验。

## 阶段二十二：引用消息深度支持 (Phase 22: Quote Context Injection) [x]
- [x] 混合路径解析：识别 Webhook 推送中的 `repliedMsg` 与 `quote`。
- [x] 远程内容补全：实现基于 DingTalk OpenAPI 的引用文本主动拉取。
- [x] 内容智能清洗：自动解析引用文本中的 JSON/卡片格式。
- [x] 验证上下文注入效果。

## 阶段二十三：本地历史辅助引用找回 (Local History Recovery) [x]
- [x] 在 `DingTalkChannel` 中建立发送消息 ID 映射表。
- [x] 实现当 OpenAPI 404 时，从本地缓存或历史文件找回引用内容。
- [x] 优化 `msgId` 到内容的本地关联逻辑。

## 阶段二十四：安审白名单与误杀优化 (Security Policy Tuning) [x]
- [x] 分析 `Output Auditor` 拦截“你不对”回复的根本原因（LLM 幻觉或正则过严）。
- [x] 实施 Master 用户特定的安审豁换逻辑。
- [x] 确保在注入引用上下文时，不会因为标记格式触碰安审红线。

## 阶段二十七：上下文过载与记忆治理 (Phase 27: Context & Memory Governance) [x]
- [x] **子阶段 A：配置优化 (会话降噪) [x]**
    - [x] 修改 `config.json` 调优滑动窗口参数 (`sessionMaxMessages: 60`, `sessionClearToSize: 40`)
    - [x] 配置生效验收 (检查模型接收的历史记录长度变化)
- [x] **子阶段 B：会话拦截 (历史文本瘦身) [x]**
    - [x] 修改 `nanobot/session/manager.py` 实现历史工具结果裁剪 (>1500字符自动截断)
    - [x] 验证超长 `tool_result` 在历史记录中是否被正确截断
- [x] **子阶段 C：记忆治理 (逻辑重构与安全) [x]**
    - [x] 重构 `nanobot/agent/memory.py` 的 Global 更新逻辑（两阶段提炼、空值拦截、新事实优先）
    - [x] 实现 `Guest Memory` 强制压缩 Prompt 约束
    - [x] 增加代码级物理守卫 (防止 None/空值写入)
    - [x] 最终回归验收 (冲突覆盖与空更新场景)

## 阶段二十八：记忆架构清理与事实一致性优化 (Phase 28: Memory Architecture Cleanup & Consistency) [x]
- [x] 评估废弃文件 (`MEMORY.md`, `USER.md`) 并重新设计基于角色的双层模型方案
- [x] 彻底清理代码中的遗留废弃文件生成逻辑
- [x] 依据 `staff_memory_philosophy.md` 初始化 `guest_template.md` (吸收了旧 user 模板要素) 与基于双区裁判的 `global.md` 骨架
- [x] 修订相关代码，实现新的记忆模板下发写入、群聊客体专属逻辑以及冲突拦截
- [x] 验证优化效果
- [x] **追加任务**：DEBUG 排查 `history.md` 近期不持续更新停止追加的原因，并约束客体沙盒的维度还原脱节问题（V5 方案已落地生效）

## 阶段二十九：优化 Heartbeat 和梦境提纯消息机制 (Phase 29: Heartbeat & Reflection Optimization) [x]
- [x] 梳理 Heartbeat 与梦境提纯在 heartbeat/service.py 和 cli/commands.py 中的流程机制
- [x] 屏蔽梦境提纯开始时的通知（即去除 is_subconscious=True 时的 start_msg）
- [x] 增强梦境提纯结束时的通知，在结果中简要带入提纯总结以便查阅
- [x] 发送通知，等待用户确认执行计划
- [x] 修改代码并验证测试
- [x] **追加任务**：将此类通知消息的发送逻辑抽象为一个通用的工具，通过此工具发送的消息不需要保存到session中，以节省token消耗。

## 阶段三十：MCP 调用参数补全与超时增强 (MCP Optimization) [x]
- [x] **执行超时修正**：将工具执行超时 (`tool_timeout`) 从 30s 提升至 180s。
- [x] **连接超时修正**：修改 `mcp.py` 使 SSE 连接超时与配置同步，解决长耗时调用中断问题。
- [x] **配置化落地**：在 `config.json` 中为 `engi_mcp` 完成 180s 超时注入。

## 阶段三十一：访客首聊引导与信息确定性同步 (Guest Onboarding & Sync) [x]
- [x] **方案定义 (Definition Phase)** [x]
  - [x] 更新 `.agents/docs/interaction_spec.md`与 `functional_spec.md` 定义首聊 SOP 与字段锚点。
  - [x] **[NEW]** 细化画像字段：部门名称支持动态根解析与全量路径转译，根文案对齐为“总公司”。
- [x] **影响分析 (Impact Analysis Phase)** [x]
  - [x] 验证 `Guest Sandbox` 隔离机制及其对确定性同步的支持。
  - [x] 确立 DingTalk API 缓存策略（`_dept_names`）规避频限。
- [x] **功能实施 (Execution Phase)** [x]
  - [x] **[BUG FIX] 画像同步架构偏移与次生回归修复** [x]
    - [x] **缺陷深度追溯 (Deep RCA)**: 定位引入 `AttributeError` 的具体对话断面 (Request 3) 和代码回退点。
    - [x] **架构方案纠偏**: 提交《建议解决方案》V6，确保逻辑回归 Agent 层并恢复解耦。
    - [x] **影子代码清理**: 移除了 `venv` 中导致修改失效的 `nanobot` 影子包。
    - [x] **回归缺陷修复**: 修正了 `dingtalk.py` (AttributeError) 和 `context.py` (NameError) 中的代码手误。
    - [x] **代码执行与验证**: 获取用户确认后，执行最终修复并验证画像物理回写功能。
    - [x] 撤销 `commands.py` / `manager.py` / `dingtalk.py` 的不当注入
    - [x] 在 `AgentLoop._process_message` 实现同步拦截
  - [x] **首次接触识别 (First Contact)**: 已在 `ContextBuilder` 中通过磁盘文件存在性感知并注入 SOP。
  - [x] **确定性同步集成 (Deterministic Sync)**:
    - [x] **[BUG FIX] 组织架构路径解析异常**: 修复 `get_user_org_path` 中的类型混淆错误。
    - [x] **[NEW] 画像回写加固 (Atomic Rewrite)**: 实现基于锚点（Section-based）的原子化段落重写，彻底解决换行错位。
    - [x] 集成 `department/get` 接口获取部门名称（修正 `name` vs `dept_name` 字段差异）。
    - [x] 注入内存缓存 `_dept_names` 优化 API 配额消耗。
    - [x] 集成 `department/listparentbyuser` 接口获取组织架构全路径。
    - [x] **实时入站同步**: 借助 `pre_process_hook` 实现第一轮对话前物理更新画像，无需“预取注入”冗余子任务。
  - [x] **梦境提纯 (Legacy Concept)**: 关于部门提取的提纯逻辑已废弃，由确定性同步物理取代。
    - [x] 优化反思逻辑，确保画像信息包含完整的组织架构路径。
    - [x] 画像持久化：将部门名称及层级结构写入 `guest/{id}.md`。
  - [x] **设计同步 (Design Extraction)**: 完成会话设计变更向 `.agents/docs` 核心文档的同步，包含 ADR 记录。

## 阶段三十二：项目调度人格与场景验证 (PM Scheduling & Scenario Validation) [Needs Review]
- [ ] **方案设计：调度算法与人格闭环 (Design Phase)**
  - [ ] 定义“高级项目调度员”复合人格：具备目标分解、资源匹配、计划制定、执行跟踪、复盘沉淀的全链路逻辑。
  - [ ] 更新 `.agents/docs/functional_spec.md`，确立任务管理协议。
- [ ] **环境注入：强化调度工具集 (Capability Phase)**
  - [ ] 在系统 Prompt 中注入“调度逻辑框架”，使其具备分配与跟进的主动性，而非仅被动接受指令。
- [ ] **场景实测：基于“项目管理”场景的闭环验证 (Validation Phase)**
  - [ ] 验证全流程：根据目标分解任务 -> 匹配资源 -> 制定计划 -> 分配任务 -> 定期跟踪 -> 总结汇报 -> 评价复盘 -> 沉淀经验。
  - [ ] 最终产出：验证 Staff 是否能通过该能力在项目管理场景中高效协作，并不断优化经验 RAG。

## 阶段三十三：Sanitizer 性能优化 (Sanitizer Performance Optimization) [Needs Review]
- [ ] **性能分析与优化 (Performance Phase)**
  - [ ] 解决 Sanitizer 在访客模式下响应时间过长的问题，优化审计预判与模型调用策略。
  - [ ] 解决 Promise intent check tool 响应时间过长的问题，优化审计预判与模型调用策略。

## 阶段三十四：上下文权重优化与“长短期记忆”协调 (Context Weight & Awareness) [/]
- [x] **基础设施：全量对话快照输出功能已实现** [x]
- [/] **现状诊断**：分析 Staff 对近距上下文理解能力差、交流“无感”的根本原因。
  - [x] 源码层审查：`nanobot/session/manager.py` 与 `nanobot/agent/context.py` [x]
  - [x] 样本快照分析：`debug_20260308_174802_839303.json` 诊断 [x]
  - [ ] 输出《上下文权重优化分析报告及实施方案》(ADR-034) [Needs Review]
- [ ] **逻辑重构**：
  - [x] **[B. Map 增量抽取逻辑重塑]**
    - 创建新的 `_EXTRACT_MEMORY_DELTAS_TOOL`
    - 修改 `consolidate` 函数：只将增量事实打上色彩标后抽取（作为 Phase 1）
  - [x] **[C. Reduce 语义合并与压缩重塑]**
    - 创建新的 `_MERGE_MEMORY_TOOL`
    - 增加严格的 Prompt Guardrails：根据 `is_master` 参数，动态锁定对 `global.md` 区1的编辑权限。要求执行去重及浓缩合并（作为 Phase 2）。
  - [x] **[E. 双引擎联合调试与验收 (Verification)]**
    - 创建沙箱测试用例 `test_memory_engine.py` 并隔离验证
    - 确立 Qwen3 模型与 Litellm 包装器的 `tool_calls` 高速接驳机制
    - 验证 YAML Head 保护与结构化合并能力

## 阶段四十一：记忆域强解耦与梦境提纯高阶进化 (Phase 41) [In Progress]
- [x] **[A. Markdown锚点解耦与 YAML 提权]**
  - **目标**：将所有强类型身份数据（Name, DeptPath, Title 等）上移至 `guest.md` 的 YAML 文件头，剥离物理引擎对 Markdown 主体的侵袭。
- [x] **[B. 领域模板 (`guest_template.md`) 重塑]**
  - **目标**：清洗模板，破除静态的“简历式”占据体，只保留四大语义区块供大模型自我发挥。
- [x] **[C. 梦境提纯架构赋能 (Nightly Purify)]**
  - **目标**：夜间批处理将厚重的记忆提取为极速“画像摘要 (Profile Summary)”。
  - **【架构释疑：对冲冷启动路由的判定耗时】**：在判断一句话该用“冷加载(快照)”还是“热加载(原本全文档)”时，若是动用大语言模型本身去做意图探险，其数百毫秒的 TTFT（首字延迟）就会抹平冷加载省下的时间。因此，实施时必须在加载引擎边缘侧搭建一片 **超轻量规则防火墙（或基于本地毫秒级小参数 Classifier）**：纯闲聊/字符少于 15/无特指名词直接下沉冷处理。核心路由本身极轻！！
- [x] **回归验收**：通过底层逻辑剥离验证了优化效果。

## 阶段三十五：工作区路径重塑与认知对齐 (Workspace Path Alignment) [x]
- [x] **路径纠偏**：彻底移除代码中对 `memory/tickets/` 等硬编码路径的引用。
- [x] **动态解析**：在 `context.py` 中实现基于 `workspace.resolve()` 的全路径提示词展示。
- [x] **逻辑回归**：将工单与心跳文件回归至 `workspace/` 根目录下，符合扁平化物理结构。
- [x] **架构同步**：更新所有关联设计文档（ADR），确立“物理路径动态解析”原则。

## 阶段三十六：实时监控网页开发 (Website Monitor Development) [x]
- [ ] **规划阶段**
  - [x] 详细调研数据来源和格式
  - [x] 编写《功能说明书》和《交互说明书》
  - [x] 提出技术实施方案并获取用户确认 [x]
  - [x] 集成服务启动逻辑至主脚本 `start.sh` [x]
- [ ] **实施阶段**
- [x] **实施阶段**
  - [x] 初始化 `/website/monitor` 目录结构
  - [x] 编写基础 CSS 样式系统 (Vanilla CSS, Premium Design)
  - [x] 实现数据读取接口（模拟或文件读取逻辑）
  - [x] 开发前端页面组件
    - [x] 对话状态面板
    - [x] 后台任务面板
    - [x] 工单状态列表
    - [x] Heartbeat 待办任务列表
  - [x] 增加实时刷新/轮询机制
- [x] **验证阶段**
  - [x] 验证页面数据准确性
  - [x] 校验 UI 展示效果和交互体验
  - [x] 编写 Walkthrough 文档

## 阶段三十八：人设设定优化与职能扩展 (Personality & Capability Expansion) [x]
- [x] **方案定义 (Definition Phase)**
  - [x] 更新 `.agents/docs/interaction_spec.md` 和 `.agents/docs/functional_spec.md` 确立访客模式下的“力所能及”主动服务行为准则。
- [x] **功能实施 (Execution Phase)**
  - [x] [MODIFY] 修改 `nanobot/agent/context.py` 注入新的访客模式职能 Prompt，明确其可辅助联系人与发送通知。
  - [ ] [VERIFY] 校验 `send_cross_chat` 与 `search_contacts` 在访客模式下的调用触发稳定性。
- [ ] **验证回归 (Verification Phase)**
  - [ ] 模拟访客请求（联系某人），验证 Staff 是否能主动出击而非被动婉拒。

## 阶段三十九：工单系统 V3 全面重构与闭环通知 (Three-Party Lifecycle & Feedback Loop) [Needs Review]
- [ ] **方案定义 (Definition Phase)**
  - [x] 深度调研三方同步机制与状态机需求
  - [x] 编写并发布《工单系统 V3 重构实施方案》 (V3 + Feedback Loop) [/]
  - [ ] 完善异常逻辑。如heartbeat失败多次应该怎么办、heartbeat的历史记录怎么保存、过期的工单如何处理等
  - [ ] 获取用户确认并授权 (V3 Implementation Plan)
- [ ] **功能实施 (Execution Phase)**
  - [ ] [MODIFY] `tickets.py`: 升级 Schema 支持三方元数据与细分状态 (PENDING, APPROVED, RUNNING, COMPLETED, FAILED, REJECTED)
  - [ ] [TicketManager]: 核心逻辑解耦，增加三方同步通知引擎
  - [ ] [ResolveTicketTool]: 实现多态审批与反馈，不再仅依赖特定标签
  - [ ] [NEW] `RejectTicketTool`: 增加驳回功能及配套通知
  - [ ] [HeartbeatService]: 闭环认领状态监控与执行反馈
- [ ] **验证回归 (Verification Phase)**
  - [ ] 自动化测试验证三方通知触发器
  - [ ] 手动闭环演练: 访客请求 -> Master 审批 -> Staff 执行 -> 三方自动同步
  - [ ] 编写 V3 验收 Walkthrough 文档

## 阶段四十：双阶段记忆流引擎重构 (Phase 40: Map-Reduce Memory Consolidation) [/]
- [x] **子阶段 A：方案探究与认知对齐 (Definition Phase)** [x]
  - [x] 提出硬编码去重方案并探讨。
  - [x] 收敛并确认最终大方案：基于 LLM 原生抽提的 Map-Reduce 两阶段融合柔性架构 (ADR-040)。
- [/] **子阶段 B：Map(第一阶段) 增量抽取逻辑重塑** [/]
  - [ ] 去除大模型单次全量重写的权限边界。
  - [ ] 在 `memory.py` 设计极简的“纯净对话增量碎片提取”Prompt。
  - [ ] 拦截并捕获 JSON 格式的 Fact Delta (增量情况)。
- [ ] **子阶段 C：Reduce(第二阶段) 语义压缩与写入闭环** [ ]
  - [ ] 设计“档案编辑长”Prompt（Merge-Conflict Resolution）。
  - [ ] 实现针对 `Guest Sandbox` 及 `Global` 记忆，用旧文档与事实增量对撞生成全新浓缩版文件并覆写。
- [ ] **子阶段 D：去除冗余干扰链路 (Reflection Refactoring)** [ ]
  - [ ] 剥除 `nanobot/agent/reflection.py` 潜意识中重写全集档案的副产物逻辑，使其退化为纯信用打分/预警服务，消除对去重方案的杂音干扰。
## 阶段四十二：智能体级定时任务前置校验与裁决架构 (Phase 42: Autonomous Validated Cron Architecture)
- [ ] **子阶段 A：方案定义与固化 (Definition & Persistence)**
  - [x] 在 `.agents/docs/task.md` 拆分出此宏大目标的验证步骤。
  - [x] 更新 `.agents/docs/functional_spec.md` 固化三段式引擎与能力校验的架构模型。
  - [x] [ADD] 创建专属白皮书：在 `.agents/docs/autonomous_cron_engine.md` 详细落盘此**前置校验与审判级路由**架构设计。
  - [x] 获得架构共识。
- [ ] **子阶段 B：底层结构改造 (Core Structure Migration)**
  - [x] [MODIFY] 修改 `nanobot/cron/types.py` 中的 `CronPayload`，移除旧版 `message`，引入 `task_content` (str), `stop_condition` (str), `required_tools` (list[str]) 等核心字段。
  - [x] [MODIFY] 修改 `nanobot/cron/service.py` 里的落库及读库映射（兼容旧记录的平滑过渡），保证时间轮依然能把新结构取回。
  - [x] 验收：人工检查 `jobs.json` 序列化是否正确映射并加载完毕。
- [ ] **子阶段 C：前置武器库校验机制 (Pre-flight Tools Validation)**
  - [x] [MODIFY] 修改 `nanobot/agent/loop.py`，向新建的 `CronTool` 注入实例时的技能树名称集合 `list(self.tools.keys())`。
  - [x] [MODIFY] 重构 `nanobot/agent/tools/cron.py` 的接口约束：明确要求输入三个新参数，并建立拦截门：若传来的 `required_tools` 在系统可用列表外，抛出异常阻断创建，要求模型调整。
  - [x] 验收：故意让大模型设定一个死循环但需要它用到 `send_sms` 的不存在工具的任务，观察是否精准拦截报错。
- [ ] **子阶段 D：唤醒即审判运行时 (Arbitration Runtime)**
  - [x] [MODIFY] 修改 `nanobot/cli/commands.py` 里的 `on_cron_job`：设计二阶段 Prompt。第一阶段喂入 `stop_condition` 触发模型自带工具探查；
  - [x] [MODIFY] 接驳输出 `[ACTION: STOP]` 或 `[ACTION: CONTINUE]`。对前者实施 `cron.remove_job(job.id)` 早夭；对后者则继续将 `task_content` 当做独立 Prompt 激活。
  - [x] 验收：挂起一个带真实停止条件的任务，并满足该条件，观察下一次到达时间点时系统会不会默默摘除任务而不是发送消息。
- [x] **子阶段 D.2：重构为纯解耦二段调用 (Two-Phase Decoupling Refactor)**
  - [x] [MODIFY] 修改 `nanobot/cli/commands.py` 里的 `on_cron_job`：拆分为 `Phase 1 (裁判所)` 和 `Phase 2 (执行器)` 两次独立的 `agent.process_direct` 调用。
  - [x] [MODIFY] Phase 2 调用时，仅发送纯粹的 `Task Content`，杜绝任何判定逻辑污染发信内容。
- [x] **子阶段 E：前置信息赋能 (Read Message Context)**
  - [x] [ADD] 在 `nanobot/agent/tools/cross_chat.py` 中新增 `ReadRecentMessagesTool`，使其能抽取目标 `sessions/dingtalk:id.md` 中的近期对话记录。
  - [x] [MODIFY] 在 `nanobot/agent/loop.py` 补充注册 `ReadRecentMessagesTool`。
  - [x] 验收：人工脚本模拟调用该工具能够成功萃取 N 行近期上下文，彻底闭环智能条件判断。

## 阶段四十三：系统任务安全审查豁免与权限加固 (Phase 43: System Task Sanitizer Bypass) [x]
- [x] **子阶段 A：方案分析与路由重构 (Design & Routing)**
  - [x] 修改 `nanobot/agent/loop.py`，使 `_process_message` 支持 `is_system_internal` 标志以透传信任。
  - [x] 优化 `process_direct` 及其调用链，确保系统自发指令（Cron/Heartbeat）在入站时携带信任指纹。
- [x] **子阶段 B：权限边界校验优化 (Master Identity Fix)**
  - [x] 修复 Master ID 在跨频道（Channel）调用时可能出现的身份误判，确保其在 `_process_message` 中稳定 bypass Sanitizer。
- [x] **子阶段 C：回归测试与安全性验证 (Verification)**
  - [x] 验证：建立包含敏感关键词的定时任务，观察其是否能在不触发拦截的情况下成功执行。
  - [x] 验证：确保正常访客的恶意消息依然受到 Sanitizer 的严格审查。

## 阶段四十四：定时任务控制台可视化展示 (Phase 44: Cron Jobs Dashboard Integration) [x]
- [x] **子阶段 A：方案探究与架构设计 (Definition Phase)**
  - [x] 分析如何将 `cron/jobs.json` 安全、实时地透传给本地监控面板进程 (`nanobot/utils/monitor_loop.sh`) 或交由前端轮询读取。
  - [x] 编写实施方案，规划新面板的 UI 展示（包含：任务名称、触发频率、终止条件与目标受众）。
- [x] **子阶段 B：数据桥接与采集层 (Data Bridge)**
  - [x] 修改 `monitor_loop.sh`，使其能够实时聚合或复制目前的 `jobs.json` 状态供 Web 伺服器呈现。
- [x] **子阶段 C：前端视图层重构 (UI Development)**
  - [x] 修改 `website/monitor/index.html`，在响应式网格中分配“定时任务 (Cron Jobs)”的专属视图区块。
  - [x] 增加 JS 渲染引擎：将 `nextRunAtMs` 转化为人类可读的倒计时，高亮展示 `stop_condition` 及目标发送人 `to`。
- [x] **子阶段 D：回归验收 (Verification)**
  - [x] 通过 CLI 或修改 JSON 模拟新建/删除定时任务，观察监控大屏是否做到即时响应。

## 阶段四十五：LLM 输入载荷优化与交互去剧本化 (LLM Input & Interaction Optimization) [x]
- [x] **第一阶段：基础清理与 Bug 修复 (Easy)** [x]
    - [x] **Task 1.1: 修复 Metadata 注入 Bug (拦截机制优化)**
    - [x] **Task 1.2: 剔除失效 Skills 载荷 (Token 降噪)**
- [x] **第二阶段：人设去剧本化 (Medium)** [x]
    - [x] **Task 2.1: 重写 `SOUL.md` (回归员工本质)**
    - [x] **Task 2.2: 重写 `AGENTS.md` (口语化准则)**
    - [x] **Task 2.3: 风格验证与回归测试**
- [x] **第三阶段：动态裁剪与分层控制 (Hard)** [x]
    - [x] **Task 3.1: Master 模式 Prompt 动态精简**
    - [x] **Task 3.2: 实施历史消息瘦身与时间感知同步** [x]
    - [x] **Task 3.3: 核心消息摘要压缩机制**

## 阶段四十七：记忆专家技能解耦与 RAG 架构重塑 (Phase 47: Memory Expert & RAG Refactor) [x]
- [x] **方案定义与解耦设计**：确立“影子日志 (Shadow Log)” + “记忆专家技能”的冷热分离架构。
- [x] **基础设施建设**：实现 `raw_history` 影子备份，确保对话 100% 物理留存。
- [x] **技能封装与迁移**：创建 `staff_memory_expert` 技能，完成检索、画像读取及提纯逻辑的剥离。
- [x] **内核瘦身与 RAG 切换**：修改 `ContextBuilder` 停止全量注入 Body，切换为工具驱动的按需调阅。
- [x] **最终清理与归档**：物理删除内核冗余代码，收缩 Session 窗口（180->45）。


## 阶段四十六：设计变更提取与文档同步 (Extract-Design-Change) [x]
- [x] 提取“时间感知标签”设计逻辑至 `session_management_spec.md`。
- [x] 提取“I/O 锁优化与 Provider 超时”逻辑至 `response_mechanism.md`。
- [x] 同步更新 `task.md` 进度。
