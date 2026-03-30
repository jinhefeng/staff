# workspace/skills/staff_memory_expert/logic.py
from __future__ import annotations
import json
import re
import asyncio
from pathlib import Path
from typing import Any, TYPE_CHECKING
from loguru import logger
from nanobot.agent.tools.base import Tool
from nanobot.utils.helpers import safe_filename, ensure_dir

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.session.manager import Session

class SearchChatHistoryTool(Tool):
    """Search full raw chat history from shadow logs."""
    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._raw_history_dir = workspace / "sessions" / "raw_history"
        self._current_user_id: str = ""
        self._current_is_master: bool = False

    def set_context(self, user_id: str, is_master: bool) -> None:
        self._current_user_id = user_id
        self._current_is_master = is_master

    @property
    def name(self) -> str: return "search_chat_history"

    @property
    def description(self) -> str:
        return "Search the full, uncut raw chat history from the Shadow Log using a keyword."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Keyword to search for."},
                "target_id": {"type": "string", "description": "Master only: Specific target userId."},
                "context_lines": {"type": "integer", "description": "Number of surrounding messages.", "default": 2}
            },
            "required": ["keyword"],
        }

    async def execute(self, keyword: str, target_id: str | None = None, context_lines: int = 2, **kwargs: Any) -> str:
        search_target = target_id or self._current_user_id
        if not self._current_is_master and search_target != self._current_user_id:
            return "Error: Permission denied."
        safe_key = safe_filename(f"dingtalk_{search_target}")
        path = self._raw_history_dir / f"{safe_key}.jsonl"
        if not path.exists(): return f"No shadow log found for {search_target}."
        try:
            results = []
            with open(path, "r", encoding="utf-8") as f:
                messages = [json.loads(line) for line in f]
            kw = keyword.lower()
            for i, msg in enumerate(messages):
                if kw in str(msg.get("content", "")).lower():
                    start, end = max(0, i - context_lines), min(len(messages), i + context_lines + 1)
                    snippet = messages[start:end]
                    res = [f"{'>> ' if s == msg else '   '}[{str(s.get('role', 'UNKNOWN')).upper()}]: {s.get('content', '')}" for s in snippet]
                    results.append(f"--- Match at {msg.get('timestamp', '')[:16]} ---\n" + "\n".join(res))
            return "\n\n".join(results[:5]) if results else f"No matches for '{keyword}'."
        except Exception as e: return f"Error: {e}"

class QueryGlobalKnowledgeTool(Tool):
    """Retrieve snippets from global knowledge memory (global.md)."""
    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._global_file = workspace / "memory" / "core" / "global.md"

    @property
    def name(self) -> str: return "query_global_knowledge"

    @property
    def description(self) -> str:
        return "Search or retrieve sections from the Global Knowledge base (global.md)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Keyword to search."},
                "full_read": {"type": "boolean", "description": "Returns the entire document.", "default": False}
            }
        }

    async def execute(self, keyword: str | None = None, full_read: bool = False, **kwargs: Any) -> str:
        if not self._global_file.exists(): return "Global base empty."
        try:
            content = self._global_file.read_text(encoding="utf-8")
            if full_read: return content
            if not keyword:
                headers = re.findall(r'^(#+ .*)$', content, re.MULTILINE)
                return "Index:\n" + "\n".join(headers)
            sections = re.split(r'\n(?=###|##)', content)
            matches = [s for s in sections if keyword.lower() in s.lower()]
            return "\n\n---\n\n".join(matches[:3]) if matches else f"No matches for '{keyword}'."
        except Exception as e: return f"Error: {e}"

class ReadFullProfileTool(Tool):
    """Read full profile details for a specific guest memory sandbox."""
    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._current_user_id: str = ""
        self._current_is_master: bool = False

    def set_context(self, user_id: str, is_master: bool) -> None:
        self._current_user_id = user_id
        self._current_is_master = is_master

    @property
    def name(self) -> str: return "read_full_profile"

    @property
    def description(self) -> str:
        return "Read the full details of a Guest Memory sandbox (guest.md)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"user_id": {"type": "string", "description": "Target userId."}}
        }

    async def execute(self, user_id: str | None = None, **kwargs: Any) -> str:
        target = user_id or self._current_user_id
        if not self._current_is_master and target != self._current_user_id:
             return "Error: Permission denied."
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', target)
        path = self._workspace / "memory" / "guests" / f"{safe_id}.md"
        if not path.exists(): return f"No profile for {target}."
        try: return path.read_text(encoding="utf-8")
        except Exception as e: return f"Error: {e}"

class ConsolidateMemoryTool(Tool):
    """Migrated Consolidation logic (Map-Reduce) from MemoryStore to Skill."""

    def __init__(self, workspace: Path):
        self._workspace = workspace
        from nanobot.agent.memory import MemoryStore
        self._mem_store = MemoryStore(workspace)

    @property
    def name(self) -> str: return "consolidate_memory"

    @property
    def description(self) -> str:
        return "Internal tool: Consolidate session messages into long-term memory via Map-Reduce."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_user_id": {"type": "string"},
                "is_master": {"type": "boolean"},
            },
            "required": ["target_user_id"]
        }

    async def execute(self, target_user_id: str, is_master: bool = False, **kwargs: Any) -> str:
        # Note: This tool is typically called programmatically by loop.py
        # It replicates the Map-Reduce flow formerly in MemoryStore.consolidate
        return "Memory consolidation logic ported to Skill. Triggered via internal API."

    async def run_consolidation(
        self,
        session: Session,
        provider: LLMProvider,
        model: str,
        memory_window: int = 50,
        current_user_id: str = "Unknown",
        is_master: bool = False
    ) -> bool:
        """The actual implementation of the Map-Reduce consolidation."""
        # --- Preparation ---
        anchor_idx = -1
        if session.last_consolidated_id:
            for i, m in enumerate(session.messages):
                if m.get("metadata", {}).get("dingtalk_msg_id") == session.last_consolidated_id:
                    anchor_idx = i
                    break
        
        safe_buffer = getattr(session, "session_safe_buffer", 20)
        end_idx = len(session.messages) - safe_buffer
        if end_idx <= anchor_idx + 1: return False

        old_messages = session.messages[anchor_idx + 1 : end_idx]
        if not old_messages: return False

        lines = []
        for m in old_messages:
            content = m.get("content")
            if not content: continue
            lines.append(f"[{m.get('timestamp', '')[:16]}] {m['role'].upper()}: {str(content)[:1000]}")

        # --- PHASE 1: MAP (Extract Deltas) ---
        from nanobot.agent.memory import _EXTRACT_MEMORY_DELTAS_TOOL
        prompt_map = f"Process interaction snippet:\n{chr(10).join(lines)}\nExtract history_entry and extracted_facts."
        
        try:
            resp_map = await provider.chat(
                messages=[{"role": "system", "content": "Precise data extractor."}, {"role": "user", "content": prompt_map}],
                tools=_EXTRACT_MEMORY_DELTAS_TOOL, model=model
            )
            if not resp_map.has_tool_calls: return False
            
            args = resp_map.tool_calls[0].arguments
            if isinstance(args, str): args = json.loads(args)
            
            if entry := args.get("history_entry"):
                self._mem_store.append_history(entry)
            facts = args.get("extracted_facts", [])
            
            # Advance cursor
            session.last_consolidated_id = old_messages[-1].get("metadata", {}).get("dingtalk_msg_id")
            if not facts: return True

            # --- PHASE 2: REDUCE (Merge) ---
            from nanobot.agent.memory import _MERGE_MEMORY_TOOL
            current_global = self._mem_store.read_global()
            current_guest, _ = self._mem_store.read_guest(current_user_id)
            
            prompt_reduce = f"""You are the Master Archive Editor. Deeply merge new factual fragments into the existing documents.

## TARGET TEMPLATE STRUCTURE (MUST FOLLOW)
1. YAML Header: TrustScore, Name, Email, Title, DeptPath, Alias, LastSyncDate.
2. Section: ## 🎭 核心辨识与标签
3. Section: ## 🛠️ 行为偏好与沟通禁忌 [Preferences]
4. Section: ## 🛡️ 专属外交策略 [Tailored Narrative]
5. Section: ## 📝 近期未决留存 [Unresolved Issues]

## 1. Current Global Knowledge Base
{current_global or "(empty)"}

## 2. Current Exclusive Memory Sandbox for User {current_user_id}
{current_guest}

## 3. NEW Incremental Fact Deltas to Merge (MUST USE CHINESE)
{chr(10).join([f"- {f}" for f in facts])}

## Editing Directive
- [LANGUAGE]: The output for Guest Sandbox MUST be in CHINESE.
- [STRUCTURE]: You MUST maintain the 4 sections above. Do NOT output a simple list.
- [DEDUPLICATION]: Merge new facts with existing ones. Paragraphs preferred over long lists.
- [SAFETY]: Preserve YAML header. TrustScore must remain between 0-100.
"""
            resp_reduce = await provider.chat(
                messages=[{"role": "system", "content": "Rigorous archive editor. Output in Chinese."}, {"role": "user", "content": prompt_reduce}],
                tools=_MERGE_MEMORY_TOOL, model=model
            )
            
            if resp_reduce.has_tool_calls:
                args_red = resp_reduce.tool_calls[0].arguments
                if isinstance(args_red, str): args_red = json.loads(args_red)
                
                if update := args_red.get("guest_memory_update"):
                    self._mem_store.write_guest(current_user_id, update)
                if global_upd := args_red.get("global_knowledge_update"):
                    # Basic Master protection check here or in Skill logic
                    if is_master or "1. Master 认定的绝对真相" not in current_global:
                         self._mem_store.write_global(global_upd)
            return True
        except Exception as e:
            logger.error("Skill consolidation failed: {}", e)
            return False
