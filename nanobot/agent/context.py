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
            parts.append(f"# 技能系统 (Skills)\n\n以下技能扩展了你的能力。详细说明请通过 `read_file` 读取对应的 `SKILL.md`。\n\n{skills_summary}")

        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self, is_master: bool = False, memory_context: str = "", current_user_id: str = "") -> str:
        """Get the core identity section — metadata only."""
        workspace_path = str(self.workspace.expanduser().resolve())
        project_root = str(Path(workspace_path).parent)
        builtin_skills_path = str(Path(project_root) / "nanobot" / "skills")
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.python_version()}"
        
        mode_label = "【首长模式 (MASTER MODE)】" if is_master else "【访客模式 (GUEST MODE)】"

        return f"""# {self.agent_name} 🐈

你是 {self.agent_name}，一名专业、可靠且高效的数字幕僚。
当前处于 {mode_label}。

## Runtime
{runtime}

## 环境与路径 (Environment & Paths)
- Root: {project_root}
- Workspace: {workspace_path}
- Global Memory: {workspace_path}/memory/core/global.md
- Guest Memory: {workspace_path}/memory/guests/{{user_id}}.md
- History: {workspace_path}/memory/HISTORY.md
- Tickets: {workspace_path}/tickets/active_tickets.json
- Heartbeat: {workspace_path}/HEARTBEAT.md

### 技能路径 (Skills)
- Built-in: {builtin_skills_path}/{{name}}/SKILL.md
- Custom: {workspace_path}/skills/{{name}}/SKILL.md

**注意**: 详细的行为准则、工具调用红线、岗位 SOP 已加载于下方的引导文件中。请务必优先遵循已加载的指令。"""

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
    
    def _format_relative_time(self, msg_ts: str) -> str:
        """格式化相对时间标签，采用分档逻辑以优化 Prompt Cache 命中率。"""
        if not msg_ts:
            return ""
        
        try:
            # 兼容 ISO 格式 (T) 和 空格分隔格式
            ts_clean = msg_ts.replace("T", " ")[:19]
            dt = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return ""

        diff = datetime.now() - dt
        seconds = int(diff.total_seconds())

        if seconds < 60:
            return "[刚才]"
        
        minutes = seconds // 60
        if minutes < 5:
            return "[5分钟内]"
        if minutes < 10:
            return "[10分钟内]"
        if minutes < 30:
            return "[30分钟内]"
        if minutes < 60:
            return "[1小时内]"
        
        hours = minutes // 60
        if hours < 24:
            return f"[{hours}小时前]"
        
        return f"[{diff.days}天前]"

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
        
        clean_history = []
        for m in history:
            msg = dict(m)
            # 消除重复：如果历史里已经存了当前消息（从 loop.py 的即时存盘逻辑而来），切除它
            if msg.get("role") == "user" and msg.get("content") == current_message and m == history[-1]:
                continue
            
            # 注入相对时间权重标签
            ts_label = self._format_relative_time(msg.get("timestamp", ""))
            if ts_label:
                content = msg.get("content")
                if isinstance(content, str):
                    msg["content"] = f"{ts_label} {content}"
                elif isinstance(content, list):
                    # 处理带媒体的复杂消息结构
                    new_content = []
                    for part in content:
                        new_part = dict(part)
                        if new_part.get("type") == "text":
                            new_part["text"] = f"{ts_label} {new_part['text']}"
                        new_content.append(new_part)
                    msg["content"] = new_content
            
            # 移除 LLM 不需要的时间戳字段，保持 Payload 干净
            msg.pop("timestamp", None)
            clean_history.append(msg)

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
