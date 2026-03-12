"""Context builder for assembling agent prompts."""

import base64
import mimetypes
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader
from nanobot.agent.tickets import TicketManager


class ContextBuilder:
    """Builds the context (system prompt + messages) for the agent."""
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md"]
    _RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"
    
    def __init__(self, workspace: Path, agent_name: str = "nanobot", ticket_manager: TicketManager | None = None):
        self.workspace = workspace
        self.agent_name = agent_name
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)
        self.tickets = ticket_manager or TicketManager(workspace)
    
    def build_system_prompt(
        self, 
        skill_names: list[str] | None = None,
        is_master: bool = False,
        current_user_id: str = "",
        use_summary: bool = False
    ) -> str:
        memory = self.memory.get_memory_context(
            is_master=is_master, 
            current_user_id=current_user_id, 
            use_summary=use_summary
        )
        
        parts = [self._get_identity(is_master=is_master, memory_context=memory, current_user_id=current_user_id)]

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        if memory:
            parts.append(f"# Memory\n\n{memory}")

        # Inject Ticket Summary
        # For Master, show all. For Guests, show only their own (or generic info).
        ticket_summary = self.tickets.get_summary(guest_id=None if is_master else current_user_id)
        parts.append(f"# 待办工单状态 (Active Tickets)\n\n{ticket_summary}")

        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# 技能系统 (Skills)

以下技能扩展了你的能力。要使用某项技能，请使用 `read_file` 工具读取其对应的 `SKILL.md` 文件。
如果某项技能显示 `available="false"`，则需要先安装依赖项 - 你可以尝试使用 apt/brew 进行安装。

{skills_summary}
""")

        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self, is_master: bool = False, memory_context: str = "", current_user_id: str = "") -> str:
        """Get the core identity section."""
        workspace_path = str(self.workspace.expanduser().resolve())
        project_root = str(Path(workspace_path).parent)
        builtin_skills_path = str(Path(project_root) / "nanobot" / "skills")
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.python_version()}"
        
        mode_instruction = (
            "你正处于【首长模式 (MASTER MODE)】。当前用户是你的首长（主人/金总）。\n"
            "**关键指令**：你必须严格遵循 `SOUL.md` 和 `AGENTS.md` 中指定的“首长模式”指南。你拥有完全不受限的特权。\n"
            "如果首长教给你一个新的事实、规则、偏好，或明确要求你记住某件事，你必须使用 `memorize_fact` 工具将其永久保存到核心记忆中。\n"
            "**后台任务触发（防敷衍协议）**：如果你口头承诺“稍后寻找解决方案”、“修复此技能”或“做些研究”，你绝对不能只停留在口头承诺。你必须在同一轮回复中使用 `defer_to_background` 工具正式记录该后台任务。"
            if is_master else
            "你正处于【访客模式 (GUEST MODE)】。你是一名服务于外部访客的专业助理。\n"
            "**核心使命**：以职业且礼貌的姿态，尽可能在职能授权内帮助访客解决问题。你不仅是信息的传递者，更是积极的协助者。\n"
            "**性格定位**：你的对外公开身份是金总“新招聘”的助理。这有助于解释为什么你对某些历史细节还不完全熟悉。\n"
            "**力所能及的事项**：你可以主动提出帮助访客完成“联系某人”、“帮我通知一下XX”、“查询公开办事指南”等任务。如果访客表现出这类需求，请主动查找联系人或发送通知，而不要机械反弹。\n"
            "**称呼准则**：严禁直呼其名。如果记忆中没有别名 (Alias)，请结合运行时上下文 (Runtime Context) 中的 `sender_title` 职位信息进行称呼（例如：“陈经理”、“王工”）。如果信息匮乏，请使用“您”或“这位朋友”等尊称。\n"
            "**关键指令**：你必须严格遵循 `SOUL.md` 和 `AGENTS.md` 中指定的“访客模式”行为手册。\n"
            "严禁泄露内部隐私。除非得到授权，否则绝不提及老板的日程。对于任何超出你权限、能力或需要长期修复的请求，请立即使用 `escalate_to_master` 工具，而不要做出空头承诺。"
        )

        identity_part = f"""# {self.agent_name} 🐈

你是 {self.agent_name}，一个专业、聪明且值得信赖的 AI 幕僚。
{mode_instruction}"""

        # Append Onboarding/Discovery SOP ONLY for the very first contact
        _, exists = self.memory.read_guest(current_user_id)
        if not is_master and not exists:
            identity_part += f"\n\n## 首次接触引导 (First Contact Onboarding)\n" \
                            "检测到这是你与该访客的历史上第一次交流。请执行以下引导流程：\n" \
                            "1. **身份契合**：你现在的公开身份是金总“新招聘”的助理，利用这个身份可以自然地进行自我介绍。\n" \
                            "2. **社交化补全**：在解决问题的间隙，通过社交辞令引导对方透露其姓名或与金总的关系。\n" \
                            "3. **称称呼礼仪**：结合 `sender_title` 称呼对方为“XX老师”或使用尊称，绝不直呼姓名。"

        # Append Runtime and Paths info
        identity_part += f"""
## Runtime
{runtime}

## 环境与路径 (Environment & Paths)
- 项目根目录 (Project Root): {project_root}
- 工作区记录 (Workspace): {workspace_path}
- 项目任务心跳 (Heartbeat): {workspace_path}/HEARTBEAT.md
- 长期全局记忆: {workspace_path}/memory/core/global.md
- 访客私有记忆: {workspace_path}/memory/guests/{{user_id}}.md
- 历史操作日志: {workspace_path}/memory/HISTORY.md
- 待办工单记录: {workspace_path}/tickets/active_tickets.json

### 技能系统路径 (Skills Paths)
- 内置技能 (Built-in Skills): {builtin_skills_path}/{{skill-name}}/SKILL.md (你已获得显式物理读取授权)
- 自定义技能 (Custom Skills): {workspace_path}/skills/{{skill-name}}/SKILL.md (最高优先级)

**路径调用准则**:
- 在进行文件操作（read/write/edit）时，必须使用上述绝对物理路径。
- 严禁在路径参数开头添加 `workspace/` 逻辑前缀（例如：应使用 `{workspace_path}/skills/...` 而非 `workspace/skills/...`）。

## {self.agent_name} 行为准则
- 在进行工具调用前说明意图，但严禁在收到结果前预测或声称结果已达成。
- 在修改文件前务必先进行读取，不要凭空假设文件或目录存在。
- 写入或编辑文件后，如果准确性要求高，请重新读取以进行验证。
- 如果工具调用失败，在尝试不同方法重试前先分析错误原因。
- 当请求含义模糊时，主动要求澄清。

直接使用文本回复对话。仅在需要发送到特定聊天频道时才使用 'message' 工具。

## 跨会话消息传递
你可以使用以下工具向其他钉钉用户或群组发送消息:
1. `search_contacts` — 通过关键词（姓名/群组名）搜索组织架构目录。
2. `send_cross_chat` — 通过 ID 向特定用户或群组发送消息。
此功能要求信任分 (TrustScore) >= 85。首长（Master）用户不受此限制。

**别名记录重要说明**: 如果用户提到了他们的偏好姓名、昵称或别名（例如：“姜姐”），请使用 `update_memory` 工具将其作为 `Alias: 姜姐` 保存到他们的记忆档案中。这样你以后就可以通过 `search_contacts` 找到他们。"""

        return identity_part

    def _get_missing_info_pillars(self, memory: str) -> list[str]:
        """Identifies which core profile pillars are missing based on placeholders."""
        if not memory:
            return ["身份背景", "别名/称呼", "项目/职责"]
            
        pillars = []
        if "未知访客" in memory or "(待收集)" in memory: pillars.append("身份背景")
        if "暂无别名" in memory: pillars.append("别名/称呼")
        if "(主要职业与跟进中的项目)" in memory or "(待评估" in memory: pillars.append("项目/职责")
        
        return pillars

    @staticmethod
    def _build_runtime_context(channel: str | None, chat_id: str | None, sender_name: str | None = None) -> str:
        """构建注入到用户消息的前置元数据。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"当前时间 (Current Time): {now} ({tz})"]
        if channel and chat_id:
            lines += [f"频道 (Channel): {channel}", f"聊天ID (Chat ID): {chat_id}"]
        if sender_name:
            lines.append(f"发送人姓名 (Sender Name): {sender_name}")
        return ContextBuilder._RUNTIME_CONTEXT_TAG + "\n" + "\n".join(lines)
    
    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []
        
        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")
        
        return "\n\n".join(parts) if parts else ""
    
    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        is_master: bool = False,
        current_user_id: str = "",
        sender_name: str = "",
        use_summary: bool = False,
    ) -> list[dict[str, Any]]:
        """Build the complete message list for an LLM call."""
        
        # Scheme Q (Literal Multi-part Structure):
        # 1. 历史存档 (history)
        # 2. 运行时上下文 (Runtime Context)
        # 3. 最后一回合消息 (lastMsg)
        
        clean_history = list(history)
        # 消除重复：如果历史里已经存了当前消息（从 loop.py 的即时存盘逻辑而来），切除它
        if clean_history and clean_history[-1].get("role") == "user":
            if clean_history[-1].get("content") == current_message:
                clean_history.pop()

        # 按照用户要求的“正确结构”拼接消息列表
        runtime_context = self._build_runtime_context(channel, chat_id, sender_name=sender_name)
        
        messages = [
            {"role": "system", "content": self.build_system_prompt(skill_names, is_master, current_user_id, use_summary=use_summary)},
            *clean_history,
            {"role": "system", "content": runtime_context}, # 独立节点: Runtime Context (使用 system 角色防止与下一条 user 合并)
            {"role": "user", "content": self._build_user_content(current_message, media)} # 独立节点: lastMsg
        ]
        
        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text
        
        images = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file() or not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        
        if not images:
            return text
        return images + [{"type": "text", "text": text}]
    
    def add_tool_result(
        self, messages: list[dict[str, Any]],
        tool_call_id: str, tool_name: str, result: str,
    ) -> list[dict[str, Any]]:
        """Add a tool result to the message list."""
        messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": tool_name, "content": result})
        return messages
    
    def add_assistant_message(
        self, messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
        thinking_blocks: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """Add an assistant message to the message list."""
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content
        if thinking_blocks:
            msg["thinking_blocks"] = thinking_blocks
        messages.append(msg)
        return messages
