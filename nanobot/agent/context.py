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


class ContextBuilder:
    """Builds the context (system prompt + messages) for the agent."""
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md"]
    _RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"
    
    def __init__(self, workspace: Path, agent_name: str = "nanobot"):
        self.workspace = workspace
        self.agent_name = agent_name
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)
    
    def build_system_prompt(
        self, 
        skill_names: list[str] | None = None,
        is_master: bool = False,
        current_user_id: str = ""
    ) -> str:
        """Build the system prompt from identity, bootstrap files, memory, and skills."""
        parts = [self._get_identity(is_master=is_master)]

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        memory = self.memory.get_memory_context(is_master=is_master, current_user_id=current_user_id)
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")

        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")

        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self, is_master: bool = False) -> str:
        """Get the core identity section."""
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.python_version()}"
        
        mode_instruction = (
            "You are operating in MASTER MODE. The current user is your boss (Master).\n"
            "**CRITICAL**: You MUST read and strictly adhere to the `Master Mode` guidelines specified in `SOUL.md` and `AGENTS.md`. "
            "You have fully unchecked privileges. "
            "If the Master teaches you a new fact, rule, preference, or explicitly asks you to remember something, you MUST use the `memorize_fact` tool to save it permanently to the Core Memory.\n"
            "**BACKGROUND TASKING (ANTI-LIP-SERVICE)**: If you verbally promise to 'look for a solution later', 'fix this skill', or 'do some research', YOU MUST NOT ONLY SAY IT. "
            "You MUST use the `defer_to_background` tool to officially log the background task in the exact same turn."
            if is_master else
            "You are operating in GUEST MODE. You are a professional assistant serving external guests.\n"
            "**CRITICAL**: You MUST read and strictly adhere to the `Guest Mode` behavioral manual specified in `SOUL.md` and `AGENTS.md`. "
            "Never leak private information. Never mention the Boss's schedule unless authorized. "
            "For any requests exceeding your authority, capability, or requiring long fixes, use the `escalate_to_master` tool IMMEDIATELY instead of just making empty promises."
        )

        return f"""# {self.agent_name} 🐈

You are {self.agent_name}, a helpful AI assistant.
{mode_instruction}

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Long-term memory: {workspace_path}/memory/MEMORY.md (write important facts here)
- History log: {workspace_path}/memory/HISTORY.md (grep-searchable). Each entry starts with [YYYY-MM-DD HH:MM].
- Active tickets: {workspace_path}/memory/tickets/active_tickets.json (JSON format, read this file to check pending escalated tickets/工单)
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md

## {self.agent_name} Guidelines
- State intent before tool calls, but NEVER predict or claim results before receiving them.
- Before modifying a file, read it first. Do not assume files or directories exist.
- After writing or editing a file, re-read it if accuracy matters.
- If a tool call fails, analyze the error before retrying with a different approach.
- Ask for clarification when the request is ambiguous.

Reply directly with text for conversations. Only use the 'message' tool to send to a specific chat channel.

## Cross-Session Messaging
You can send messages to other DingTalk users or groups using:
1. `search_contacts` — search the organization directory by keyword (name / group name)
2. `send_cross_chat` — send a message to a specific user or group by their ID
This capability requires TrustScore >= 85. Master users bypass this restriction.

**Important for Aliases**: If a user mentions their preferred name, nickname, or alias (e.g., "姜姐"), use the `update_memory` tool to save it into their memory profile as `Alias: 姜姐`. This allows you to find them later via `search_contacts`."""

    @staticmethod
    def _build_runtime_context(channel: str | None, chat_id: str | None, sender_name: str | None = None) -> str:
        """Build untrusted runtime metadata block for injection before the user message."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        if channel and chat_id:
            lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
        if sender_name:
            lines.append(f"Sender Name: {sender_name}")
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
    ) -> list[dict[str, Any]]:
        """Build the complete message list for an LLM call."""
        return [
            {"role": "system", "content": self.build_system_prompt(skill_names, is_master, current_user_id)},
            *history,
            {"role": "user", "content": self._build_runtime_context(channel, chat_id, sender_name=sender_name)},
            {"role": "user", "content": self._build_user_content(current_message, media)},
        ]

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
