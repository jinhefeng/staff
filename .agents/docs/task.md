# Staff (个人智能幕僚) 开发任务大纲

## 阶段一：方案定义 (Definition Phase)
- [x] 需求分析与架构设计确认
- [x] 编写《功能说明书》(functional_spec.md)
- [x] 编写《交互说明书》(interaction_spec.md)
- [x] 完善《总体架构文档》(architecture_spec.md)

## 阶段二：影响分析 (Impact Analysis)
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

## 阶段三：基于 nanobot 架构的扩展与同步 (Phase 3: Extension)
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

## 阶段四：不可抗力模型迁移与多网关并存 (Nvidia Provider Integration)
- [x] 评估制定接入计划并等候确认 (保留双芯架构)
- [x] 源码层面植入 `nvidia` 为一等公民 Provider 注册表
- [x] 覆写并重构 `start.sh` 提供双端 API Keys 配置模板并指引 `minimaxai` 切换

## 阶段五：环境规范化与部署脚本拆卸 (Phase 5: Deployment)
- [x] 架构重整：废除单文件强耦合启动。设计并编写纯净 `install.sh` 隔离构建 venv 虚拟环境及拉取依赖；编写轻量化 `start.sh` 专门司职守护运行与配置文件生成阻断机制。

## 阶段六：配置生态与交互体验优化 (Phase 6: DevEx)
- [x] 架构重整：剥离全局配置体系。将 `config.json` 本地化绑定在工程根目录，提供 `config.sample.json` 模板文件并更新 `.gitignore` 黑名单；为两份启动脚本追加详实的步骤回显语料。

## 阶段七：跨平台容器化部署 (Phase 7: Cloud Native - BLOCKED)
- [x] 彻底解耦 Windows 生态机制，放弃臃肿的 `WeChatFerry` 注入流架构路线，启动【方案 B：纯净 Gewechat 协议流】的重构。
  - [x] 编写跨平台极简 Dockerfile 封装 Nanobot 运行载体 (由于墙内基础设施全面被封禁导致构建报错)。
  - [x] 编写 `docker-compose.yml` 建立 nanobot 与官方 `gewechat` 大底座并存的双子星网络。
  - [x] 彻底移除旧代码的耦合，实现对 HTTP Hook 规范的新任通道 (`channels/gewechat.py`) 接管。

## 阶段八：半云原生混合架构回退 (Phase 8: Hybrid Native)
- [x] 分解原定的纯双子星 Docker 结构，改为 Gewechat 底座独立云化。
  - [x] 从 `docker-compose.yml` 中删去受阻的 Python `staff-bot` 业务节点，仅作微信登录凭证提供服务器用。
  - [x] 修复重构本地执行链 `install.sh`，剔除已删除死亡的 WeChatFerry 路径。
  - [x] 指南回退：打通本地宿主机端口网络，使从 `venv` 中启动的 Nanobot 能够通过 HTTP 与隔离箱里的 Gewechat 容器成功握手。

## 阶段九：独立模块解耦架构 (Phase 9: Decoupling Architecture)
- [x] 架构剥离方案提交：明确微信作为**独立微服务网关**的边界。
- [x] 改造 `nanobot` 网关：不再关注并轮询验证底层通信服务的健康状态或强制管理其生命周期，仅作为事件驱动的通信接受者 (Webhook / HTTP Interface) 与之对接。

## 阶段十：全场景通信网关插座化 (Phase 10: Plug-and-Play Gateway)
- [x] 插座与鉴权架构重设计：仿照大模型 Providers 逻辑设计多终端与微信多开群控架构，更新实现方案并恳求授权。
- [x] 改造 `nanobot/config/schema` 将原先的信道布尔配置扩充为包含 token 与 instance url 甚至 appId 的阵列映射表。
- [x] 改造 `GewechatChannel` 等系统信道层，支持从插座阵列中反向实例化并注册独立的 Webhook 事件处理器。

## 阶段十一：网关回调挂载与权证互信 (Phase 11: Webhook & Authorization)
- [x] API 鉴权双向挂载实施方案提交：明确业务侧如何自动化接管大底座的事件推送。
- [x] 改造 `nanobot` API 核心路由，对外暴露统一的 `/{instance_name}/webhook` 入站接口接收不同端点的微信事件。
## 阶段十二：终端点火与扫码准入 (Phase 12: Terminal QR Login)
- [x] 编写并提审终端扫码点火架构方案，确保符合用户“沉浸式控制台扫码”的预期。
- [x] 开发微信扫码鉴权 SDK 层（封装 Gewechat 的 `getLoginQrCode` 和 `checkLogin` 接口）。
- [x] 改造 `nanobot` CLI 命令集，新增 `nanobot channels login --channel gewechat --instance {name}` 指令以发起控制台二维码打印并轮询扫码结果。
- [x] 实现登录成功后的自动配置回填：将生成的 `app_id` 回写至 `config.json` 释放用户的心智负担。

## 阶段十三：异地解耦部署与穿透联调 (Phase 13: Distributed Deployment) - [ABANDONED]
由于底座环境的不确定性，用户已放弃基于 Gewechat 的方案。
- [x] 清理代码资产：从系统内核中彻底拔除 `GewechatChannel`、配置表残留映射及关联 CLI 指令，保证系统纯净无冗余。


## 阶段十四：钉钉企业机器人原生对接 (Phase 14: DingTalk Native Integration)
- [x] 申请：在钉钉开发者后台拉起企业内部机器人应用，并取得 `clientId` 和 `clientSecret`。
- [x] 联调：通过本地开发机运行的 webhook (18790) 配置进入钉钉开发后台的消息订阅/Stream 模式。
- [x] 配置：修改 `config.json`，停用微信并启用钉钉代理。

## 阶段十五：带权限标签的高阶混合记忆池 (Phase 15: Tag-based Shared Memory)
- [x] 架构设计：重制原生的双层文本记忆，引入 [PUBLIC], [PRIVATE:uuid], [MUST-KNOW] 等知识元结构标签。
- [x] 动态上下文洗牌机制：开发 `get_filtered_memory` 函数。
  - [x] 主人视角透视：不受限读取全部记忆。
  - [x] 访客隔离洗牌：拦截剥离属于其他用户的私密记忆，只放行 [PUBLIC] 和有关本人的条目，防止串供与嚼舌根。
- [x] 开发主副人格 Prompt 引擎：
  - [x] 主人模式：绝对服从、精简回答、执行复杂指令。
  - [x] 访客与安防模式：通过高压指令禁止越权修改标签或刺探其他人隐私。

## 阶段十六：职能白名单与 RAG 引导 (Phase 16: White List & SOP)
- [x] 信息收集：结构化提取访客意图与联系人信息。
- [x] 状态模糊查询：拦截窥探主人的精确日程，提供“正在开会”等模糊化状态。
- [x] SOP 流程引导：为特定词汇（如立项、报销）返回 RAG 标准指南。

## 阶段十七：安全审计与 Prompt 净化层 (Phase 17: Sanitizer & Audit)
- [x] 防注入屏障层：在访客模式下前置丢弃/改写涉及“忽略之前指令、查看数据库”等攻击意图。
- [x] 脱敏输出审查：对即将发给外部访客的内容进行二次校验，防止泄露私密决策权。

## 阶段十八：异步跟进工单与超时安抚 (Phase 18: Asynchronous Auto-Pacifier)
- [x] 异步等待环闭环逻辑：阅读、生成提案 -> 转发给主人 -> 等待批示 -> 实际对外回复。
- [x] 超时触发器：编写 cron/heartbeat 钩子，监控长时间未决议事项。
- [x] 安抚文案生成：超时发生时，主动向访客发送“事已加急，老板暂未脱身”等关怀话术。

## 阶段十九：联邦记忆系统与物理隔离 (Phase 19: Federated Memory Isolation)
- [x] 将原先的统一单点 `MEMORY.md` 切分为网状分布式文件结构。
  - 主脑全域：`memory/core/global.md`
  - 客体专域：`memory/guests/{id}.md`
- [x] 对所有的 `ContextBuilder` 进行底层路径劫持替换，确保 Guest 面对 LLM 时绝不可能通过文件系统访问其他人员档案。
- [x] 在客体记忆头部建立量化的 YAML 标签标头，初始化包含信任度 `TrustScore: 50`。

## 阶段二十：潜意识反思网关 (Phase 20: Subconscious Reflection Gateway)
- [x] 创建一个内部隐藏运转的独立 `Reflection Agent`（无对外通信接口，只靠 Cron 或事件触发）。
- [x] 开发反思推盘流水线：在每日闲时将不同客体的独立存档碎片与主全域记忆进行交叉比对。
- [x] 赋予最高批判性智力：根据 `TrustScore` 和比对矛盾度，自动化增减 Guest 的信用评分，将证实信息逆向反哺入全域知识库 `global.md`，并将危险风向预警主动推送给主理人审阅。

- [x] **阶段二十一：工程架构提纯与扁平化 (Phase 21: Project Refinement)**
    - [x] 核心代码提升：将 `nanobot` 提升至根目录。
    - [x] 冗余清理：删除 `src`、`vendor` 等无效层级目录。
    - [x] 自动化适配：更新 `install.sh` 与 `start.sh` 的路径依赖。
    - [x] 语法与启动校验。

## 阶段二十二：引用消息深度支持 (Phase 22: Quote Context Injection)
- [x] 混合路径解析：识别 Webhook 推送中的 `repliedMsg` 与 `quote`。
- [x] 远程内容补全：实现基于 DingTalk OpenAPI 的引用文本主动拉取。
- [x] 内容智能清洗：自动解析引用文本中的 JSON/卡片格式。
- [x] 验证上下文注入效果。

## 阶段二十三：本地历史辅助引用找回 (Local History Recovery)
- [x] 在 `DingTalkChannel` 中建立发送消息 ID 映射表。
- [x] 实现当 OpenAPI 404 时，从本地缓存或历史文件找回引用内容。
- [x] 优化 `msgId` 到内容的本地关联逻辑。

## 阶段二十四：安审白名单与误杀优化 (Security Policy Tuning)
- [x] 分析 `Output Auditor` 拦截“你不对”回复的根本原因（LLM 幻觉或正则过严）。
- [x] 实施 Master 用户特定的安审豁免逻辑。
- [x] 确保在注入引用上下文时，不会因为标记格式触碰安审红线。


## 阶段二十七：上下文过载与记忆治理 (Phase 27: Context & Memory Governance) [/]
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

## 阶段二十八：记忆架构清理与事实一致性优化 (Phase 28: Memory Architecture Cleanup & Consistency) [/]
- [x] 评估废弃文件 (`MEMORY.md`, `USER.md`) 并重新设计基于角色的双层模型方案
- [x] 彻底清理代码中的遗留废弃文件生成逻辑
- [x] 依据 `staff_memory_philosophy.md` 初始化 `guest_template.md` (吸收了旧 user 模板要素) 与基于双区裁判的 `global.md` 骨架
- [x] 修订相关代码，实现新的记忆模板下发写入、群聊客体专属逻辑以及冲突拦截
- [/] 验证优化效果
- [x] **追加任务**：DEBUG 排查 `history.md` 近期不持续更新停止追加的原因，并约束客体沙盒的维度还原脱节问题（V5 方案已落地生效）

## 阶段二十九：优化 Heartbeat 和梦境提纯消息机制 (Phase 29: Heartbeat & Reflection Optimization) [x]
- [x] 梳理 Heartbeat 与梦境提纯在 heartbeat/service.py 和 cli/commands.py 中的流程机制
- [x] 屏蔽梦境提纯开始时的通知（即去除 is_subconscious=True 时的 start_msg）
- [x] 增强梦境提纯结束时的通知，在结果中简要带入提纯总结以便查阅
- [x] 发送通知，等待用户确认执行计划
- [x] 修改代码并验证测试
- [x] **追加任务**：将此类通知消息的发送逻辑抽象为一个通用的工具，通过此工具发送的消息不需要保存到session中，以节省token消耗。

## 阶段三十：优化MCP的token传參
- [] **DEBUG**发现很多次tool调用时没有拼接不要参数的情况，如token、ModelType等，

