"""Memory system for persistent agent memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from nanobot.utils.helpers import ensure_dir

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.session.manager import Session

import re

_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "A paragraph (2-5 sentences) summarizing key events/decisions/topics. "
                        "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search.",
                    },
                    "guest_memory_update": {
                        "type": "string",
                        "description": "Full updated markdown for the current user's exclusive memory sandbox. Ensure TrustScore YAML is kept at the top.",
                    },
                    "global_knowledge_update": {
                        "type": "string",
                        "description": "Full updated markdown for the Core Global Knowledge. Only use if instructed to update global truth (Requires Master privileges).",
                    },
                },
                "required": ["history_entry"],
            },
        },
    }
]


class MemoryStore:
    """Federated memory: core/global.md (long-term facts) + guests/{user_id}.md (isolated sandbox + trust)."""

    def __init__(self, workspace: Path):
        self.memory_dir = ensure_dir(workspace / "memory")
        self.core_dir = ensure_dir(self.memory_dir / "core")
        self.guests_dir = ensure_dir(self.memory_dir / "guests")
        self.global_file = self.core_dir / "global.md"
        self.history_file = self.memory_dir / "HISTORY.md"
        self.groups_file = self.core_dir / "groups.json"

    def load_groups(self) -> dict[str, str]:
        if self.groups_file.exists():
            try:
                return json.loads(self.groups_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save_group_info(self, group_id: str, title: str) -> None:
        """Dynamically save group title & ID for cross-chat targeting."""
        groups = self.load_groups()
        orig = groups.get(group_id)
        if orig != title:
            groups[group_id] = title
            self.groups_file.write_text(json.dumps(groups, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug("Saved group info: {} ({})", title, group_id)

    def read_global(self) -> str:
        if self.global_file.exists():
            return self.global_file.read_text(encoding="utf-8")
        return ""

    def write_global(self, content: str) -> None:
        self.global_file.write_text(content, encoding="utf-8")
        
    def _get_guest_file(self, user_id: str) -> Path:
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', user_id)
        if not safe_id:
            safe_id = "default_guest"
        return self.guests_dir / f"{safe_id}.md"

    def read_guest(self, user_id: str) -> str:
        g_file = self._get_guest_file(user_id)
        if g_file.exists():
            return g_file.read_text(encoding="utf-8")
        return "---\nTrustScore: 50\n---\n"

    def write_guest(self, user_id: str, content: str) -> None:
        g_file = self._get_guest_file(user_id)
        g_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self, is_master: bool = False, current_user_id: str = "") -> str:
        """Get filtered memory context based on identity.
        Master sees global. Guest sees global + their own specific guest file.
        """
        global_mem = self.read_global()
        
        if is_master:
            return f"## Core Memory (Master View - Full Access)\n{global_mem}"
            
        guest_mem = self.read_guest(current_user_id)
        return f"## Core Global Knowledge (Read-Only)\n{global_mem}\n\n## Your Exclusive Memory Sandbox (Read-Write)\n{guest_mem}"

    async def consolidate(
        self,
        session: Session,
        provider: LLMProvider,
        model: str,
        *,
        archive_all: bool = False,
        memory_window: int = 50,
        current_user_id: str = "UnknownGuest",
        is_master: bool = False,
    ) -> bool:
        """Consolidate old messages into MEMORY.md + HISTORY.md via LLM tool call.

        Returns True on success (including no-op), False on failure.
        """
        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info("Memory consolidation (archive_all): {} messages", len(session.messages))
        else:
            keep_count = memory_window // 2
            if len(session.messages) <= keep_count:
                return True
            if len(session.messages) - session.last_consolidated <= 0:
                return True
            old_messages = session.messages[session.last_consolidated:-keep_count]
            if not old_messages:
                return True
            logger.info("Memory consolidation: {} to consolidate, {} keep", len(old_messages), keep_count)

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}")

        current_global = self.read_global()
        current_guest = self.read_guest(current_user_id)
        
        prompt = f"""Process this conversation and call the save_memory tool with your consolidation.

## Current Global Knowledge Base (Read-Only for Guests)
{current_global or "(empty)"}

## Current Exclusive Memory Sandbox for User {current_user_id} (Read-Write)
{current_guest}

## Conversation to Process
{chr(10).join(lines)}

## Memory Philosophy Guide & Identity Context
You are maintaining a human-like associative memory. You are analyzing a conversation between the Assistant and a user with ID: {current_user_id}.

Is Master Mode: {'YES' if is_master else 'NO'}

1. If it's a fact/strategy specifically relating to the current user, or an observation about them, write it to `guest_memory_update`.
2. DO NOT lose the YAML header (e.g., `--- TrustScore: 50 ---`) when rewriting `guest_memory_update`.
3. If Is Master Mode is YES and the user gives a global fact or rule, write the new comprehensive global memory to `global_knowledge_update`.
4. If Is Master Mode is NO, you MUST NOT provide `global_knowledge_update`.
5. Apply chromatic tags to facts: [Neutral], [Caution], [Strategy].
"""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a memory consolidation agent. Call the save_memory tool with your consolidation of the conversation."},
                    {"role": "user", "content": prompt},
                ],
                tools=_SAVE_MEMORY_TOOL,
                model=model,
            )

            if not response.has_tool_calls:
                logger.warning("Memory consolidation: LLM did not call save_memory, skipping")
                return False

            args = response.tool_calls[0].arguments
            if isinstance(args, str):
                args = json.loads(args)
            if not isinstance(args, dict):
                logger.warning("Memory consolidation: unexpected arguments type {}", type(args).__name__)
                return False

            if entry := args.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                self.append_history(entry)
                
            if update := args.get("guest_memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_guest:
                    self.write_guest(current_user_id, update)

            if is_master:
                if global_upd := args.get("global_knowledge_update"):
                    if not isinstance(global_upd, str):
                        global_upd = json.dumps(global_upd, ensure_ascii=False)
                    if global_upd != current_global:
                        self.write_global(global_upd)

            session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
            logger.info("Memory consolidation done: {} messages, last_consolidated={}", len(session.messages), session.last_consolidated)
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return False
