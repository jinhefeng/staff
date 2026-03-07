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
        
        # Load from template if it doesn't exist
        template_file = self.guests_dir / "guest_template.md"
        if template_file.exists():
            content = template_file.read_text(encoding="utf-8")
        else:
            content = "---\nTrustScore: 50\n---\n"
        
        # Write it immediately so it exists for future reads in this flow
        self.write_guest(user_id, content)
        return content

    def write_guest(self, user_id: str, content: str) -> None:
        g_file = self._get_guest_file(user_id)
        g_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self, is_master: bool = False, current_user_id: str = "") -> str:
        """Get filtered memory context based on identity.
        Master sees global + their own specific guest file.
        Guest sees global + their own specific guest file.
        """
        global_mem = self.read_global()
        guest_mem = self.read_guest(current_user_id)
        
        if is_master:
            return f"## Core Memory (Master View - Full Access)\n{global_mem}\n\n## Master's Private Memory Sandbox (Read-Write)\n{guest_mem}"
            
        return f"## Core Global Knowledge (Read-Only)\n{global_mem}\n\n## Your Exclusive Memory Sandbox (Read-Write)\n{guest_mem}"

    def _is_valid_memory(self, content: str | None) -> bool:
        """Check if the memory content is valid and safe to write."""
        if not content or not isinstance(content, str):
            return False
        # Prevent common invalid LLM placeholders
        invalid_placeholders = {"none", "null", "undefined", "(empty)", "no changes", "n/a", "[]", "{}"}
        if content.strip().lower() in invalid_placeholders:
            return False
        # Basic sanity check: content should have some substance
        if len(content.strip()) < 2:
            return False
        return True

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
        """Consolidate old messages into MEMORY.md + HISTORY.md via LLM tool call."""
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
            content = m.get("content")
            if not content:
                continue
            # Basic sanitization of history lines to focus on core chat
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {content[:1000]}")

        current_global = self.read_global()
        current_guest = self.read_guest(current_user_id)
        
        prompt = f"""Process the following conversation snippet and update the agent's memory systems.

## 1. Current Global Knowledge Base (Read-Only context)
{current_global or "(empty)"}

## 2. Current Exclusive Memory Sandbox for User {current_user_id}
{current_guest}

## 3. Conversation to Process
{chr(10).join(lines)}

## Instructions:
1. **Identify NEW Facts & Profiles**: Extract any important facts, rules, or user preferences. 
   - **Persona & Profiling**: Based on the conversation, update the user's personality traits (e.g., "heavy details", "impatient", "friendly") and communication habits.
2. **Global Update (Both Master & Guests)**: 
   - Is Master Mode (with highest authority): {'YES' if is_master else 'NO'}
   - If there are new universally shared truths (e.g. general technical facts, public news), write to `global_knowledge_update`.
   - **CRITICAL DOUBLE-LAYER RULES**:
     - The global markdown MUST have two predefined sections: "### 👑 1. Master 认定的绝对真相" and "### 👥 2. 客体/群体共识总结的真相".
     - If you are in **Master Mode (YES)**: You are authorized to overwrite or append to Section 1 (Master Absolute Truths) with Master's rulings.
     - If you are NOT in Master Mode (NO): You are strictly **forbidden** from modifying Section 1. You may only summarize and add general non-private consensus facts into Section 2.
     - If no new global info is found, just return the exact `current_global` content.
3. **Guest Sandbox**: 
   - Update `guest_memory_update` using EXACTLY the following Markdown structure. Do NOT invent new headings:
     ### 🎭 基本特质与履历 (Persona & Basic Info)
     ### 🛠️ 行为偏好与沟通习惯 (Preferences)
     ### 🛡️ 专属口径与应对策略 (Tailored Narrative)
     ### 📝 近期互动与挂机状态 (Recent Context & Unresolved Issues)
   - **Tagged Knowledge**: Maintain and use structural colored tags:
     - `[NEUTRAL]`: Facts or simple observations.
     - `[CAUTION]`: Taboos or sensitive topics for this user.
     - `[STRATEGY]`: Communication instructions/narrative overrides.
   - **Precedence & Secrets**: If Master instructed you to keep a secret from this guest or lie, put it under "Tailored Narrative" with `[STRATEGY]`. If it contradicts Global Section 1, the Strategy is the absolute truth *for this guest only*.
   - **Safety**: ALWAYS preserve the YAML header (e.g., `--- TrustScore: 50 ---`). Keep the total length concise.
4. **Safety Guard**: NEVER return "None", "null", or empty strings for memory updates.
"""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a senior memory architect. Your goal is to consolidate session history while ensuring data integrity and enforcing the dual-layer truth mechanism."},
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
                return False

            # 1. Update History.md (Log)
            if entry := args.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                self.append_history(entry)
                
            # 2. Update Guest Memory (Compacted)
            if update := args.get("guest_memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                
                # Auto-recovery: If TrustScore header is missing but present in current_guest,补全它
                import re
                old_header_match = re.match(r'^(---\n.*?\n---)', current_guest, re.DOTALL)
                new_header_match = re.match(r'^(---\n.*?\n---)', update, re.DOTALL)
                
                if old_header_match and not new_header_match:
                    logger.info("Memory consolidation: Auto-restoring TrustScore header for {}", current_user_id)
                    update = f"{old_header_match.group(1)}\n{update}"

                # Defensive check: Ensure it's not a placeholder
                if self._is_valid_memory(update) and update != current_guest:
                    # Final check: Even after recovery, did it lose the header?
                    if "TrustScore" in current_guest and "TrustScore" not in update:
                        logger.warning("Memory consolidation: Update lost TrustScore header, rejecting")
                    else:
                        self.write_guest(current_user_id, update)

            # 3. Update Global Knowledge (Conflict Resolution & Double-Layer)
            if global_upd := args.get("global_knowledge_update"):
                if not isinstance(global_upd, str):
                    global_upd = json.dumps(global_upd, ensure_ascii=False)
                
                # Physical Guard: Only overwrite if it's valid and informative
                if self._is_valid_memory(global_upd) and global_upd != current_global:
                    # Safety check
                    if len(current_global) > 200 and len(global_upd) < 50:
                         logger.error("Memory consolidation: Detected suspicious global memory shrinkage, blocking update")
                    else:
                        # Extra security validation: If not master, forbid tampering with section 1.
                        # We use regex to extract the content of Section 1 in old and new global.
                        if not is_master:
                            import re
                            def _extract_section_1(text):
                                match = re.search(r'(###.*1\..*?真相)(.*?)(###.*2\..*?真相|$)', text, re.DOTALL)
                                return match.group(2).strip() if match else ""
                            
                            old_s1 = _extract_section_1(current_global)
                            new_s1 = _extract_section_1(global_upd)
                            if old_s1 and new_s1 and old_s1 != new_s1:
                                logger.warning("Consolidate Access Denied: Guest/Group chat attempted to modify Master Absolute Truths. Rejecting.")
                            else:
                                self.write_global(global_upd)
                        else:
                            self.write_global(global_upd)

            session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
            logger.info("Memory consolidation done: {} messages, last_consolidated={}", len(session.messages), session.last_consolidated)
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return False
