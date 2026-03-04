# Staff 系统状态总览 (System Status Overview)

> **最后更新**: 2026-03-05 00:06 CST  
> **当前版本**: nanobot-ai 0.1.4.post2 (上游最新 0.1.4.post3)  
> **运行环境**: macOS / Python 3.11 / venv 隔离

---

## 一、架构概览

```
┌──────────────────────────────────────────────────────┐
│                   DingTalk Stream                    │
│              (dingtalk-stream SDK)                   │
└────────────────────┬─────────────────────────────────┘
                     │ WebSocket
┌────────────────────▼─────────────────────────────────┐
│              NanobotDingTalkHandler                   │
│  ┌─────────────────────────────────────────────────┐ │
│  │  引用消息处理 (Quote Context Injection)           │ │
│  │  - repliedMsg 本地解析                           │ │
│  │  - OpenAPI 远程拉取 (fallback)                   │ │
│  │  - per-chat 本地缓存 (fallback)                  │ │
│  └─────────────────────────────────────────────────┘ │
└────────────────────┬─────────────────────────────────┘
                     │ InboundMessage
┌────────────────────▼─────────────────────────────────┐
│                  AgentLoop                            │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │is_master │→ │Sanitizer │→ │ContextBuilder     │  │
│  │Detection │  │(3-state) │  │(Master/Guest Mode)│  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
│  ┌──────────────────────────────────────────────────┐│
│  │             LLM Inference (litellm)              ││
│  │  Provider: anthropic/openrouter/deepseek/etc.    ││
│  └──────────────────────────────────────────────────┘│
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │Output    │  │Memory    │  │Reflection Agent   │  │
│  │Auditor   │  │Consolidat│  │(Subconscious)     │  │
│  └──────────┘  └──────────┘  └───────────────────┘  │
└──────────────────────────────────────────────────────┘
```

## 二、核心模块清单

| 模块 | 文件 | 状态 | 功能 |
|------|------|------|------|
| 身份路由 | `agent/loop.py` | ✅ | `masterIds` 判定，`is_master` flag 下发 |
| 联邦记忆 | `agent/memory.py` | ✅ | 物理隔离的 `global.md` + `guests/{id}.md` |
| 上下文构建 | `agent/context.py` | ✅ | Master/Guest 双模式 Prompt 注入 |
| 安审防火墙 | `agent/sanitizer.py` | ✅ | 三态 Input Sanitizer + Output Auditor |
| 潜意识反思 | `agent/reflection.py` | ✅ | TrustScore 推演 + 谣言检测 |
| 异步工单 | `agent/tickets.py` | ✅ | 挂起-安抚-闭环决策链 |
| 升级工具 | `agent/tools/tickets.py` | ✅ | EscalateToMaster / ResolveTicket |
| 钉钉通道 | `channels/dingtalk.py` | ✅ | Stream 模式 + 引用消息解析 |
| 配置 Schema | `config/schema.py` | ✅ | `DingTalkConfig.master_ids` 已补全 |

## 三、已知限制与遗留问题

### 钉钉引用消息三种失败场景

| 场景 | 钉钉行为 | 当前处理 |
|------|---------|---------|
| 引用用户自己的原始文字消息 | ✅ `repliedMsg.content` 有值（dict 格式） | ✅ 自动提取 `.text` 字段 |
| 引用机器人的互动卡片 | ❌ 无 content，API 404 | ⚠️ per-chat 内存缓存（重启清空） |
| 引用"回复消息"(reply-of-reply) | ❌ 无 `repliedMsg` 子对象，API 404 | ⚠️ 仅显示占位标签 |

**建议方案**: 将 per-chat 缓存持久化到文件系统，重启后可恢复。

### 安审系统

- Master 用户已实现 `is_master` 绕过（Input Sanitizer + Output Auditor）
- Guest 用户的三态安审（SAFE/BLOCK/ESCALATE）正常工作
- `<think>` 标签清洗已修复

## 四、配置要点

```json
{
  "channels": {
    "dingtalk": {
      "enabled": true,
      "clientId": "dingXXXXXXXX",
      "clientSecret": "xxxxxxxx",
      "masterIds": ["014224562537153949"],
      "memoryWindow": 30
    }
  }
}
```

> `masterIds` 对应钉钉的 `senderStaffId`（员工工号），在开发者后台可查看。

## 五、文件系统布局

```
staff/
├── .agent/
│   ├── docs/                    # 项目文档（本文件）
├── .agent/                      # 机器人指令集与文档
│   ├── docs/                    # 项目技术文档
│   │   ├── system_status.md     # [Current] 系统总览与架构
│   │   ├── staff_memory_philosophy.md  # 记忆哲学
│   │   └── ...                  # 其他部署/技术设计文档
│   ├── rules/                   # 项目规则 (代码风格/任务管理)
│   └── workflows/               # 工作流定义 (restore-context 等)
├── workspace/                   # 核心运行数据与配置 (R/W)
│   ├── AGENTS.md                # 代理角色定义与行为手册
│   ├── SOUL.md                  # 人格灵魂与核心 Prompt
│   ├── TOOLS.md                 # 提示词层面的工具描述
│   ├── HEARTBEAT.md             # 心跳任务指令
│   ├── memory/                  # 联邦记忆体系
│   │   ├── core/
│   │   │   ├── global.md        # 全局长期知识 (Master 模式写入)
│   │   │   └── groups.json      # 已识别的群组 ID/标题映射
│   │   ├── guests/              # 访客/用户私有记忆沙盒目录
│   │   └── HISTORY.md           # 归档的历史摘要 (可搜索)
│   ├── sessions/                # 会话上下文持久化记录
│   ├── tickets/                 # 异步工单与任务状态数据
│   └── skills/                  # 用户定义的技能 SKILL.md 存放地
├── nanobot/                     # 核心引擎 (基于 HKUDS/nanobot)
│   ├── agent/                   # Agent 逻辑层
│   │   ├── loop.py              # 核心主循环与身份判定
│   │   ├── context.py           # 上下文拼装路径逻辑
│   │   ├── memory.py            # 记忆归档与联邦同步逻辑
│   │   ├── reflection.py        # 潜意识反思与信任推演
│   │   ├── sanitizer.py         # 输入/输出安审防火墙
│   │   ├── subagent.py          # 子代理管理逻辑
│   │   ├── tickets.py           # 工单状态机管理
│   │   └── tools/               # 核心工具箱
│   │       ├── filesystem.py    # 文件读写改查 (工具)
│   │       ├── memory.py        # memorize_fact (工具)
│   │       ├── tickets.py       # 升级/解决工单 (工具)
│   │       ├── defer.py         # 任务后台延迟执行 (工具)
│   │       └── ...              # cron/shell/web/spawn 等工具
│   ├── bus/                     # 内部消息总线 (Events/Queue)
│   ├── channels/                # 通信通道 (DingTalk/CLI)
│   ├── config/                  # 配置加载与 Schema 校验
│   ├── providers/               # LLM 供应商封装 (Litellm/Nvidia/Gemini)
│   ├── session/                 # 会话内存管理
│   ├── skills/                  # 系统级预置技能
│   ├── templates/               # Prompt 初始模板
│   └── utils/                   # 辅助函数库
├── config.json                  # 运行配置 (包含 API Keys/masterIds)
├── pyproject.toml               # Python 项目依赖管理
├── install.sh                   # 一键环境初始化脚本
└── start.sh                     # 服务启动与热重启脚本
```

> **实时性说明**: 该布局图反映了系统当前的物理结构，若有新模块添加或文件删除，此文档应同步更新。
