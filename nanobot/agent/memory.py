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
        """Get filtered memory context (Index/Identity only) to support RAG-flow."""
        global_content = self.read_global()
        guest_content, _ = self.read_guest(current_user_id)
        
        # 1. Extract Global Index (Headers only)
        global_index = re.findall(r'^(#+ .*)$', global_content, re.MULTILINE)
        global_idx_str = "\n".join(global_index) if global_index else "(Empty)"
        
        # 2. Extract Guest Identity (YAML Header only)
        header_match = re.match(r'^(---\n.*?\n---)', guest_content, re.DOTALL)
        guest_identity = header_match.group(1) if header_match else "No identity metadata."
            
        if is_master:
            return f"## Core Memory Index (Full Access)\n{global_idx_str}\n\n## Master Identity Metadata\n{guest_identity}"
            
        return f"## Shared Knowledge Index (Read-Only)\n{global_idx_str}\n\n## Your Identity Snapshot\n{guest_identity}"

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
