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

    def read_guest(self, user_id: str) -> tuple[str, bool]:
        """Read guest memory. Returns (content, exists)."""
        g_file = self._get_guest_file(user_id)
        if g_file.exists():
            return g_file.read_text(encoding="utf-8"), True
        
        # Load from template if it doesn't exist
        template_file = self.guests_dir / "guest_template.md"
        if template_file.exists():
            content = template_file.read_text(encoding="utf-8")
        else:
            content = "---\nTrustScore: 50\nLastSyncDate: \"\"\n---\n"
        
        # Write it immediately so it exists for future reads in this flow
        self.write_guest(user_id, content)
        return content, False

    def update_guest_deterministic(self, user_id: str, updates: dict[str, Any]) -> None:
        """Deterministically update guest memory fields (metadata and content).
        Directly manipulates YAML and text to avoid LLM hallucination.
        """
        content, _ = self.read_guest(user_id)
        
        # 1. Update YAML Header
        header_match = re.match(r'^(---\n.*?\n---)', content, re.DOTALL)
        if header_match:
            header_str = header_match.group(1)
            body_str = content[len(header_str):]
            
            # Simple YAML parser-like logic for our controlled schema
            for key, val in updates.items():
                if key in ["TrustScore", "LastSyncDate"]:
                    pattern = rf"^{key}:.*$"
                    if re.search(pattern, header_str, re.MULTILINE):
                        header_str = re.sub(pattern, f"{key}: {val}", header_str, flags=re.MULTILINE)
                    else:
                        # Append before the closing ---
                        header_str = header_str.replace("\n---", f"\n{key}: {val}\n---")
            
            content = header_str + body_str

        # 1. Section extraction
        # We target the section between '### 🎭 基本特质与履历' and the next '###'
        marker = "### 🎭 基本特质与履历"
        if marker not in content:
            content += f"\n\n{marker}\n"
        
        # Split content into parts: before, section, after
        # Safely capture everything BEFORE the marker
        marker_idx = content.find(marker)
        before_marker = content[:marker_idx]
        rest = content[marker_idx + len(marker):]
        
        # Find where the next section starts
        next_section_pos = rest.find("\n###")
        if next_section_pos != -1:
            section_content = rest[:next_section_pos]
            after_section = rest[next_section_pos:]
        else:
            section_content = rest
            after_section = ""

        # 2. Parse existing KV and schema
        # schema: (internal_key, Display Label, [Search Patterns])
        schema = [
            ("name", "Name (姓名)", [r"Name\s*\(姓名\)", r"Name", r"姓名"]),
            ("email", "Email (邮箱)", [r"Email\s*\(邮箱\)", r"Email", r"邮箱"]),
            ("title", "Title (职位)", [r"Title\s*\(职位\)", r"Title", r"职位"]),
            ("DeptPath", "DeptPath (组织架构)", [r"DeptPath\s*\(组织架构\)", r"DeptPath"]),
        ]
        
        kv_map = {}
        # Parse existing values to preserve them if not in 'updates'
        for key, display, patterns in schema:
            combined = "|".join(patterns)
            match = re.search(rf"(?m)^([- \t]*(\*\*)?({combined})(\*\*)?:\s*)(.*)$", section_content)
            if match:
                kv_map[key] = match.group(5).strip()

        # 3. Apply updates
        schema_keys = [s[0] for s in schema]
        for k, v in updates.items():
            if k in schema_keys:
                kv_map[k] = str(v).strip().replace("\n", " ").replace("\r", "")

        # 4. Reconstruct the clean section
        new_section_lines = [marker]
        for key, display, _ in schema:
            val = kv_map.get(key, "")
            new_section_lines.append(f"- **{display}**: {val}")
        
        # Preserve other non-schema fields (Identity, etc)
        # We also filter out any 'orphan' lines that were likely residuals of our schema keys
        schema_lookup_combined = "|".join([p for _, _, pats in schema for p in pats])
        
        for line in section_content.splitlines():
            clean_line = line.strip()
            if not clean_line or clean_line.startswith("###"): continue
            
            # If it's a schema field, it's already handled
            if re.match(rf"^([- \t]*(\*\*)?({schema_lookup_combined})(\*\*)?:\s*)", clean_line):
                continue
            
            # If it's an orphan line matching a value we just updated, discard it to fix the 'newline bug'
            is_orphan = False
            if not clean_line.startswith("-"):
                for val in kv_map.values():
                    if val and val in clean_line and len(clean_line) < len(val) + 5:
                        is_orphan = True
                        break
            
            if not is_orphan:
                new_section_lines.append(line)

        # 5. Assembly
        final_content = (before_marker + "\n".join(new_section_lines).strip() + "\n" + after_section).strip() + "\n"
        
        self.write_guest(user_id, final_content)
        logger.info("Atomic profile reconstruction for user {}: {}", user_id, updates.keys())

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
        guest_mem, _ = self.read_guest(current_user_id)
        
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
            # Scheme N: Robust Anchor Slicing (Configurable Safe Buffer)
            # Scheme N: Robust ID-based slicing
            # 1. Find the anchor index in current messages
            anchor_idx = -1
            if session.last_consolidated_id:
                for i, m in enumerate(session.messages):
                    if m.get("metadata", {}).get("dingtalk_msg_id") == session.last_consolidated_id:
                        anchor_idx = i
                        break
                        
            # 2. Slice messages to consolidate (excluding what's already done and what's in Safe Buffer)
            # Get safe_buffer from the session object, which was correctly synced from AgentLoop
            safe_buffer = getattr(session, "session_safe_buffer", 20)
            
            # Use the actual list length to guard against over-slicing
            # end_idx is the index up to which we archive. 
            # We must keep 'safe_buffer' messages at the end.
            end_idx = len(session.messages) - safe_buffer
            
            logger.info("Memory consolidation slicing: anchor_idx={}, end_idx={}, total={}, buffer={}, window={}", 
                        anchor_idx, end_idx, len(session.messages), safe_buffer, memory_window)

            if end_idx <= anchor_idx + 1:
                logger.info("Memory consolidation: No harvestable messages after anchor {} (index {}) with buffer {} reserved. Skipping.", 
                            session.last_consolidated_id, anchor_idx, safe_buffer)
                return False

            old_messages = session.messages[anchor_idx + 1 : end_idx]
            if not old_messages:
                return False
            logger.info("Memory consolidation: {} to consolidate (idx {} to {}), {} buffer reserved", 
                        len(old_messages), anchor_idx + 1, end_idx, safe_buffer)

        lines = [] # Initialize lines here, as it's used in both branches
        for m in old_messages:
            content = m.get("content")
            if not content:
                continue
            
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {content[:1000]}")

        current_global = self.read_global()
        current_guest, _ = self.read_guest(current_user_id)
        
        prompt = f"""Process the following conversation snippet and update the agent's memory systems.

## 1. Current Global Knowledge Base (Read-Only context)
{current_global or "(empty)"}

## 2. Current Exclusive Memory Sandbox for User {current_user_id}
{current_guest}

## 3. Conversation to Process
{chr(10).join(lines)}

## Instructions:
1. **Identify NEW Facts & Preferences**: Extract any important facts, project updates, or subjective preferences.
   - **Persona Enrichment**: Enhance user profiling using the conversation context.
   - **Relationship & Habits**: Observe their relationship with 'Gold Master' and their interaction style.
   - **Communication Habits**: Note if they prefer brevity, are technical, or have specific taboos.
   Note: Objective facts like Name, Title, and Dept are now handled automatically by the system and do not need extraction.
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
                # 修复 V8：当 LLM 认为全是无意义水聊而不调用工具时，
                # 必须强行排空（ACK）并推进游标返回 True，否则会产生永远停在此处的算力黑洞死锁。
                logger.warning("Memory consolidation: LLM found no valuable context to save, bypassing extraction but advancing anchor index.")
                # We skip to the final update block to advance the cursor.
            else:
                args = response.tool_calls[0].arguments
                if isinstance(args, str):
                    args = json.loads(args)
                if not isinstance(args, dict):
                    # 如果参数彻底损坏，这种极端情况允许重试
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

                # Final Update: Shift existing pointers and record the new ID anchor (Scheme N: Robust Slicing)
            if old_messages:
                last_msg_id = old_messages[-1].get("metadata", {}).get("dingtalk_msg_id")
                if last_msg_id:
                    session.last_consolidated_id = last_msg_id
            
            logger.info("Memory consolidation done: {} messages consolidated, last_consolidated_id={}", 
                        len(old_messages), session.last_consolidated_id)
            return True
        except Exception:
            logger.exception("Memory consolidation failed")
            return False
