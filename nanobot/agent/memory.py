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

_EXTRACT_MEMORY_DELTAS_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "extract_deltas",
            "description": "Extract new facts, preferences, or sentiments from the conversation snippet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "A concise paragraph summarizing key events/topics of this snippet. Start with [YYYY-MM-DD HH:MM].",
                    },
                    "extracted_facts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of NEWLY discovered facts/preferences. MUST prefix each with [NEUTRAL], [CAUTION], or [STRATEGY]. Return empty array if nothing new.",
                    }
                },
                "required": ["history_entry", "extracted_facts"],
            },
        },
    }
]

_MERGE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "merge_memory",
            "description": "Merge extracted facts into existing knowledge documentation resolving conflicts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "guest_memory_update": {
                        "type": "string",
                        "description": "Full updated markdown for the Guest sandbox. Ensure TrustScore YAML exists at the top. Deduped and compressed.",
                    },
                    "global_knowledge_update": {
                        "type": "string",
                        "description": "Full updated markdown for Core Global Knowledge. Leave empty if no global info changed.",
                    },
                },
                "required": ["guest_memory_update"],
            },
        },
    }
]

_PRUNE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "prune_memory",
            "description": "Prune and refine bulky memory documentation by deduplicating facts and consolidating labels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "refined_content": {
                        "type": "string",
                        "description": "The complete, refined, and deduped markdown content for the guest memory file including YAML header.",
                    }
                },
                "required": ["refined_content"],
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

    def update_guest_deterministic(self, user_id: str, updates: dict[str, Any]) -> bool:
        """Deterministically update guest memory fields (metadata).
        Directly manipulates YAML header exclusively.
        """
        content, _ = self.read_guest(user_id)
        
        # 1. Update YAML Header
        header_match = re.match(r'^(---\n.*?\n---)', content, re.DOTALL)
        if header_match:
            header_str = header_match.group(1)
            body_str = content[len(header_str):]
            
            # Simple YAML parser-like logic for our controlled schema
            for key, val in updates.items():
                if not val:  # Skip empty values
                    continue
                # Normalize keys (Name, Email, DeptPath, Title, etc.) for YAML section mapping
                yaml_key = key.title() if key.lower() in ['name', 'email', 'title'] else key
                
                # We dynamically update ANY passed key in the YAML header
                pattern = rf"(?m)^{yaml_key}:.*$"
                str_val = str(val).strip().replace('\n', ' ')
                if re.search(pattern, header_str):
                    header_str = re.sub(pattern, f"{yaml_key}: {str_val}", header_str)
                else:
                    # Append before the closing ---
                    header_str = header_str.replace("\n---", f"\n{yaml_key}: {str_val}\n---")
            
            content = header_str + body_str
            self.write_guest(user_id, content)
            logger.info("Atomic YAML profile reconstruction for user {}: {}", user_id, list(updates.keys()))
            return True
        else:
            logger.warning("No YAML header found in guest memory for {}. Skipping updates.", user_id)
            return False

    def write_guest(self, user_id: str, content: str) -> None:
        g_file = self._get_guest_file(user_id)
        g_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def _get_guest_summary_file(self, user_id: str) -> Path:
        summary_dir = self.guests_dir / "summaries"
        summary_dir.mkdir(parents=True, exist_ok=True)
        return summary_dir / f"{user_id}.md"

    def read_guest_summary(self, user_id: str) -> tuple[str, bool]:
        """Read the guest profile summary."""
        s_file = self._get_guest_summary_file(user_id)
        if s_file.exists():
            return s_file.read_text(encoding="utf-8"), True
        return "", False

    def write_guest_summary(self, user_id: str, content: str) -> None:
        """Write the distilled guest profile summary."""
        self._get_guest_summary_file(user_id).write_text(content, encoding="utf-8")

    def get_memory_context(self, is_master: bool = False, current_user_id: str = "", use_summary: bool = False) -> str:
        """Get filtered memory context based on identity, supporting Cold-Boot profiling."""
        global_mem = self.read_global()
        
        guest_mem = ""
        tag = ""
        # Apply cold-boot memory routing: heavily trims context window
        if use_summary and not is_master:
            summary, exists = self.read_guest_summary(current_user_id)
            if exists:
                guest_mem = summary
                tag = " [COLD BOOT: Profile Snapshot Only]"
        
        # Fallback to full document if no summary exists or if master
        if not guest_mem:
            guest_mem, _ = self.read_guest(current_user_id)
            
        if is_master:
            return f"## Core Memory (Master View - Full Access)\n{global_mem}\n\n## Master's Private Memory Sandbox (Read-Write)\n{guest_mem}"
            
        return f"## Core Global Knowledge (Read-Only)\n{global_mem}\n\n## Your Exclusive Memory Sandbox (Read-Write){tag}\n{guest_mem}"

    async def purify_guest_memory(self, user_id: str, provider, model: str) -> bool:
        """Nightly Purify: Compress the bulky guest.md into a highly distilled profile summary snapshot."""
        import re
        guest_mem, exists = self.read_guest(user_id)
        if not exists or len(guest_mem) < 300:
            return False  # Skip already small profiles
            
        header_match = re.search(r'^(---\n.*?\n---)', guest_mem, re.DOTALL)
        yaml_header = header_match.group(1) if header_match else ""
        
        prompt = f'''You are a master profile summarizer. Compress the following bulky guest memory document into an ultra-concise snapshot (max 150 words). 
Focus strictly on:
1. Core persona/identity
2. Critical preferences or restrictions (Taboos)
3. Actionable strategy for the assistant

CRITICAL RULES:
- Reply with ONLY the Markdown content. Do NOT wrap in ```markdown blocks if possible.
- The output MUST fit within a single glance and represent the "Cold-Boot" state of this person.

## Source Document
{guest_mem}'''
        
        try:
            resp = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.1
            )
            summary_content = resp.content.strip() if resp.content else ""
            
            # Strip wrapper
            if summary_content.startswith("```markdown"):
                summary_content = summary_content[11:]
            elif summary_content.startswith("```"):
                summary_content = summary_content[3:]
            if summary_content.endswith("```"):
                summary_content = summary_content[:-3]
                
            final_summary = f"{yaml_header}\n\n{summary_content.strip()}"
            self.write_guest_summary(user_id, final_summary)
            logger.info("Nightly purify generated summary snapshot for guest={}", user_id)
            return True
        except Exception as e:
            logger.error("Failed to purify guest memory for {}: {}", user_id, e)
            return False

    async def prune_guest_memory(self, user_id: str, provider: LLMProvider, model: str) -> bool:
        """Memory Pruning: Deeply refine and deduplicate the guest.md file, directly overwriting it.
        Focuses on merging redundant labels [CAUTION], [STRATEGY] and discarding chitchat.
        """
        guest_mem, exists = self.read_guest(user_id)
        if not exists:
            return False

        prompt = f"""You are the Master Memory Pruner. Your goal is to refine and compact a bulky guest memory file while ensuring NO information loss for critical rules.

## Current Memory Content
{guest_mem}

## Refining Instructions
1. **Deduplication & Merging (CRITICAL)**: 
   - Scan all entries. If multiple entries (regardless of their current labels) describe the same core fact, taboo, or preference, you MUST merge them into a single, comprehensive point.
   - For `[CAUTION]` (Taboos/Red Flags) and `[STRATEGY]` (Instructions from Master), consolidate redundant warnings into a single, high-impact instruction.
2. **Fact Refining**: For `[NEUTRAL]` facts, keep only the essence. Discard transient conversational context (e.g., 'the user said hello'). 
3. **Weighting**: If entries conflict, prioritize the information that appears to be more recent or specific.
4. **Formatting**: Maintain the 4-section Markdown structure (Persona, Preferences, Tailored Narrative, Recent Status). ALWAYS preserve the exact YAML header including TrustScore.

## Goal
Reduce the total length of the document by at least 40% while making the remaining rules sharper and more coherent.
"""
        try:
            resp = await provider.chat(
                messages=[
                    {"role": "system", "content": "You refine agent memory via deduplication and consolidation. You are meticulous and never lose critical warnings."},
                    {"role": "user", "content": prompt}
                ],
                tools=_PRUNE_MEMORY_TOOL,
                model=model,
                temperature=0.1
            )

            if not resp.has_tool_calls:
                logger.warning("Prune guest memory: LLM bypassed pruning tool calls.")
                return False

            args = resp.tool_calls[0].arguments
            if isinstance(args, str): args = json.loads(args)
            refined_content = args.get("refined_content")

            if self._is_valid_memory(refined_content) and refined_content != guest_mem:
                # Atomically ensure TrustScore header is intact if it was missing in output
                old_header_match = re.match(r'^(---\n.*?\n---)', guest_mem, re.DOTALL)
                new_header_match = re.match(r'^(---\n.*?\n---)', refined_content, re.DOTALL)
                if old_header_match and not new_header_match:
                     refined_content = f"{old_header_match.group(1)}\n{refined_content}"

                if "TrustScore" not in refined_content:
                    logger.warning("Pruned content lost TrustScore YAML, rejecting write for {}", user_id)
                    return False

                self.write_guest(user_id, refined_content)
                logger.info("Memory Pruning successful for guest={}, length {} -> {}", 
                            user_id, len(guest_mem), len(refined_content))
                return True
            
            return False
        except Exception as e:
            logger.error("Failed to prune guest memory for {}: {}", user_id, e)
            return False

    def _is_valid_memory(self, content: str | None) -> bool:
        """Check if the memory content is valid and safe to write."""
        if not content or not isinstance(content, str):
            return False
        # Prevent common invalid LLM placeholders
        invalid_placeholders = {"none", "null", "undefined", "(empty)", "no changes", "n/a", "[]", "{}"}
        if content.strip().lower() in invalid_placeholders:
            return False
        # Basic sanity check: content should have some substance
        if len(content.strip()) < 10: # Increased minimum length for safety
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
        """Consolidate old messages using Map-Reduce (Extract Deltas -> Merge) architecture."""
        if archive_all:
            old_messages = session.messages
            logger.info("Memory consolidation (archive_all): {} messages", len(session.messages))
        else:
            anchor_idx = -1
            if session.last_consolidated_id:
                for i, m in enumerate(session.messages):
                    if m.get("metadata", {}).get("dingtalk_msg_id") == session.last_consolidated_id:
                        anchor_idx = i
                        break
                        
            safe_buffer = getattr(session, "session_safe_buffer", 20)
            end_idx = len(session.messages) - safe_buffer
            
            logger.info("Memory consolidation slicing: anchor_idx={}, end_idx={}, total={}, buffer={}, window={}", 
                        anchor_idx, end_idx, len(session.messages), safe_buffer, memory_window)

            if end_idx <= anchor_idx + 1:
                return False

            old_messages = session.messages[anchor_idx + 1 : end_idx]
            if not old_messages:
                return False
            logger.info("Memory consolidation: {} to consolidate (idx {} to {})", len(old_messages), anchor_idx + 1, end_idx)

        lines = []
        for m in old_messages:
            content = m.get("content")
            if not content: continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {content[:1000]}")

        # --- PHASE 1: MAP (Extract Fact Deltas) ---
        prompt_map = f"""Process the following conversation snippet. Focus strictly on extracting incremental changes.
## Conversation Snippet
{chr(10).join(lines)}

## Extraction Directive
1. Output a coherent `history_entry` summarizing the interaction.
2. Extract ANY NEW facts, user preferences, conclusions, or emotional traits into `extracted_facts`.
3. You MUST prefix each fact with a structural colored tag:
   - `[NEUTRAL]`: Normal facts, state updates.
   - `[CAUTION]`: Taboos, sensitive topics, red flags.
   - `[STRATEGY]`: Communication logic overrides, instructions from Master.
4. If this snippet is pure chitchat with no long-term persistence value, return an empty array for `extracted_facts`.
"""
        extracted_facts = []
        try:
            resp_map = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a precise data extractor. Extract pure factual deltas without assuming prior context."},
                    {"role": "user", "content": prompt_map},
                ],
                tools=_EXTRACT_MEMORY_DELTAS_TOOL,
                model=model,
            )
            
            if not resp_map.has_tool_calls:
                logger.warning("Consolidate Map Phase: LLM bypassed extraction.")
            else:
                args = resp_map.tool_calls[0].arguments
                if isinstance(args, str): args = json.loads(args)
                
                # Update history right away
                if entry := args.get("history_entry"):
                    if not isinstance(entry, str): entry = json.dumps(entry, ensure_ascii=False)
                    self.append_history(entry)
                    
                facts = args.get("extracted_facts", [])
                if isinstance(facts, list):
                    extracted_facts = [str(f) for f in facts if f]
                    
            # Advance cursor even if we didn't extract anything or failed Phase 1
            if old_messages:
                last_msg_id = old_messages[-1].get("metadata", {}).get("dingtalk_msg_id")
                if last_msg_id:
                    session.last_consolidated_id = last_msg_id
                    
            if not extracted_facts:
                logger.info("Consolidate Map Phase: No new facts extracted. Skipping Reduce phase (Cursor advanced to {}).", session.last_consolidated_id)
                return True
                
        except Exception:
            logger.exception("Consolidate Map Phase failed")
            return False

        # --- PHASE 2: REDUCE (Merge & Deduplicate) ---
        current_global = self.read_global()
        current_guest, _ = self.read_guest(current_user_id)
        
        prompt_reduce = f"""You are the Master Archive Editor. Deeply merge new factual fragments into exiting documents.

## 1. Current Global Knowledge Base (Master Access: {'YES' if is_master else 'NO'})
{current_global or "(empty)"}

## 2. Current Exclusive Memory Sandbox for User {current_user_id}
{current_guest}

## 3. NEW Incremental Fact Deltas to Merge
{chr(10).join([f"- {f}" for f in extracted_facts])}

## Editing Directive (Deduplication & Compaction)
1. **Guest Sandbox**: Integrate new facts into the 4 rigid sections (Persona, Preferences, Tailored Narrative, Recent/Status). 
   - [DEDUPLICATION]: If a new fact aligns with or repeats an existing fact, DO NOT ADD IT TWICE. Merge them into a single, polished sentence.
   - [COMPACTION]: If any section contains >4 bullet points, rewrite the entire section into a dense, cohesive paragraph to save tokens.
   - [SAFETY]: ALWAYS preserve the `--- TrustScore: XY ---` YAML header exactly as it was.
2. **Global Update**: Update `global_knowledge_update` ONLY if there are universally shared facts.
   - [RULE 1]: Global is split into "### 👑 1. Master 认定的绝对真相" and "### 👥 2. 客体/群体共识总结的真相".
   - [RULE 2 (Master Access=NO)]: You are strictly FORBIDDEN from altering Section 1. If any new fact contradicts Section 1, discard the new fact entirely! You may only append/merge into Section 2.
   - [RULE 3 (Master Access=YES)]: You have supreme authority to overwrite Section 1 to set absolute truths.
   - Ignore `global_knowledge_update` if nothing global changed.
"""
        try:
            resp_reduce = await provider.chat(
                messages=[
                    {"role": "system", "content": "You are a rigorous archive deduplicator. Merge facts flawlessly without losing information or creating redundancies."},
                    {"role": "user", "content": prompt_reduce},
                ],
                tools=_MERGE_MEMORY_TOOL,
                model=model,
            )
            
            if resp_reduce.has_tool_calls:
                args = resp_reduce.tool_calls[0].arguments
                if isinstance(args, str): args = json.loads(args)
                
                # Update Guest Memory
                if update := args.get("guest_memory_update"):
                    if not isinstance(update, str): update = json.dumps(update, ensure_ascii=False)
                    
                    # Auto-recovery for TrustScore YAML
                    import re
                    old_header_match = re.match(r'^(---\n.*?\n---)', current_guest, re.DOTALL)
                    new_header_match = re.match(r'^(---\n.*?\n---)', update, re.DOTALL)
                    if old_header_match and not new_header_match:
                        logger.info("Consolidate Reduce: Auto-restoring TrustScore header for {}", current_user_id)
                        update = f"{old_header_match.group(1)}\n{update}"

                    if self._is_valid_memory(update) and update != current_guest:
                        if "TrustScore" not in update:
                            logger.warning("Consolidate Reduce: Update lost TrustScore header, rejecting")
                        else:
                            self.write_guest(current_user_id, update)

                # Update Global Knowledge
                if global_upd := args.get("global_knowledge_update"):
                    if not isinstance(global_upd, str): global_upd = json.dumps(global_upd, ensure_ascii=False)
                    
                    if self._is_valid_memory(global_upd) and global_upd != current_global:
                        if len(current_global) > 200 and len(global_upd) < 50:
                             logger.error("Consolidate Reduce: Detected suspicious global memory shrinkage, blocking update")
                        else:
                            if not is_master:
                                import re
                                def _extract_section_1(text):
                                    match = re.search(r'(###.*1\..*?真相)(.*?)(###.*2\..*?真相|$)', text, re.DOTALL)
                                    return match.group(2).strip() if match else ""
                                old_s1 = _extract_section_1(current_global)
                                new_s1 = _extract_section_1(global_upd)
                                if old_s1 and new_s1 and old_s1 != new_s1:
                                    logger.warning("Consolidate Reduce Denied: Guest attempted to modify Master Absolute Truths. Rejecting global update.")
                                else:
                                    self.write_global(global_upd)
                            else:
                                self.write_global(global_upd)
            else:
                logger.warning("Consolidate Reduce Phase: LLM bypassed merging.")
                
            logger.info("Memory consolidation done: Map-Reduce cycle completed (last_consolidated_id={})", session.last_consolidated_id)
            return True
        except Exception:
            logger.exception("Consolidate Reduce Phase failed")
            return False
