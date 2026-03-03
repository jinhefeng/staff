# Staff 系统状态总览 (System Status Overview)

> **最后更新**: 2026-03-03 02:38 CST  
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
      "masterIds": ["014224562537153949"]
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
│   │   ├── system_status.md     # 系统总览
│   │   ├── staff_memory_philosophy.md  # 记忆哲学
│   │   ├── staff_memory_tech_design.md # 记忆技术设计
│   │   └── dingtalk_deploy_guide.md    # 钉钉部署指南
│   ├── rules/                   # 项目规则
│   └── workflows/               # 工作流定义
├── nanobot/                     # 核心引擎（基于 HKUDS/nanobot 二次开发）
│   ├── agent/                   # Agent 核心
│   │   ├── loop.py              # 主循环 + 身份路由
│   │   ├── context.py           # 上下文构建器
│   │   ├── memory.py            # 联邦记忆系统
│   │   ├── sanitizer.py         # 安审防火墙
│   │   ├── reflection.py        # 潜意识反思
│   │   └── tickets.py           # 异步工单
│   ├── channels/
│   │   └── dingtalk.py          # 钉钉通道
│   ├── config/
│   │   └── schema.py            # 配置 Schema
│   └── templates/
│       └── SOUL.md              # 人格灵魂 Prompt
├── config.json                  # 本地配置（.gitignore）
├── pyproject.toml               # Python 包定义
├── install.sh                   # 环境安装
└── start.sh                     # 启动脚本
```
