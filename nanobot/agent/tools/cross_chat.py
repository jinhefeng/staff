"""Cross-session chat tools for sending messages across DingTalk conversations.

Provides:
- SearchContactsTool: Search organization directory for users/groups
- SendCrossChatTool: Send messages to any user or group (trust score gated)
- ReadRecentMessagesTool: Read recent messages from a target user/group's session
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, TYPE_CHECKING

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage

if TYPE_CHECKING:
    from pathlib import Path


class SearchContactsTool(Tool):
    """Search DingTalk organization directory for users or groups."""

    def __init__(
        self,
        search_fn: Callable[..., Awaitable[dict[str, Any]]] | None = None,
        workspace: Path | None = None,
    ):
        """
        Args:
            search_fn: Async callable(keyword) -> {"users": [...], "groups": [...]}
            workspace: Path for accessing local memory (groups & guest aliases)
        """
        self._search_fn = search_fn
        self._workspace = workspace

    def set_search_fn(self, fn: Callable[..., Awaitable[dict[str, Any]]]) -> None:
        """Set the search function (called after channel is ready)."""
        self._search_fn = fn

    @property
    def name(self) -> str:
        return "search_contacts"

    @property
    def description(self) -> str:
        return (
            "Search the DingTalk organization directory for users or groups by keyword. "
            "Returns matching user names with IDs and group names with conversation IDs. "
            "Use this to find the target before calling send_cross_chat."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Search keyword (name, pinyin, or group name)",
                },
            },
            "required": ["keyword"],
        }

    async def execute(self, keyword: str, **kwargs: Any) -> str:
        if not self._search_fn:
            return "Error: DingTalk directory search not available (channel not started)."

        if not keyword or not keyword.strip():
            return "Error: keyword is required."

        try:
            results = await self._search_fn(keyword.strip())
        except Exception as e:
            logger.warning("API search failed/unavailable: {}", e)
            results = {"users": [], "groups": []}

        users = results.get("users", [])
        groups = results.get("groups", [])
        
        # Local memory fallback / augmentation
        if self._workspace:
            try:
                from nanobot.agent.memory import MemoryStore
                mem = MemoryStore(self._workspace)
                kw_lower = keyword.strip().lower()
                
                # 1. Alias in Guest memory
                if mem.guests_dir.exists():
                    for g_file in mem.guests_dir.glob("*.md"):
                        content = g_file.read_text(encoding="utf-8")
                        if kw_lower in content.lower():
                            uid = g_file.stem
                            if not any(u["userId"] == uid for u in users):
                                name_match = re.search(r"## Guest:\s*(.*?)\s*\(", content)
                                name = name_match.group(1).strip() if name_match else f"Alias for {uid}"
                                users.append({"name": f"{name} (Matched Local)", "userId": uid, "dept": ""})
                
                # 2. Local Group memory
                local_groups = mem.load_groups()
                for gid, gname in local_groups.items():
                    if kw_lower in gname.lower() or keyword.strip() == gid:
                        if not any(g["openConversationId"] == gid for g in groups):
                            groups.append({"name": f"{gname} (Local)", "openConversationId": gid})
                            
            except Exception as e:
                logger.error("Error searching local memory: {}", e)

        if not users and not groups:
            return f"No results found for '{keyword}'."

        parts = []
        if users:
            lines = [f"  - {u['name']} (userId: {u['userId']}, dept: {u.get('dept', 'N/A')})" for u in users]
            parts.append("**Users:**\n" + "\n".join(lines))
        if groups:
            lines = [f"  - {g['name']} (openConversationId: {g['openConversationId']})" for g in groups]
            parts.append("**Groups:**\n" + "\n".join(lines))

        return "\n\n".join(parts)


class SendCrossChatTool(Tool):
    """Send a message to a specific DingTalk user or group (cross-session).

    Requires TrustScore >= 85 for non-master users.
    """

    TRUST_THRESHOLD = 85

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        workspace: Path | None = None,
    ):
        self._send_callback = send_callback
        self._workspace = workspace
        # Set per-turn by the agent loop
        self._current_sender_id: str = ""
        self._current_is_master: bool = False

    def set_context(
        self,
        sender_id: str,
        is_master: bool,
    ) -> None:
        """Set the current requestor's context for trust validation."""
        self._current_sender_id = sender_id
        self._current_is_master = is_master

    @property
    def name(self) -> str:
        return "send_cross_chat"

    @property
    def description(self) -> str:
        return (
            "Send a message to a specific DingTalk user or group (cross-session). "
            "Use search_contacts first to find the target's ID. "
            "Requires TrustScore >= 85. Master users bypass this restriction."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_id": {
                    "type": "string",
                    "description": "The target userId (for private chat) or openConversationId (for group chat)",
                },
                "target_type": {
                    "type": "string",
                    "enum": ["user", "group"],
                    "description": "Whether the target is a 'user' (private message) or a 'group' (group message)",
                },
                "content": {
                    "type": "string",
                    "description": "The message content to send",
                },
            },
            "required": ["target_id", "target_type", "content"],
        }

    def _get_trust_score(self) -> int:
        """Read the current sender's TrustScore from their guest memory file."""
        if not self._workspace or not self._current_sender_id:
            return 0
        from nanobot.agent.memory import MemoryStore
        mem = MemoryStore(self._workspace)
        guest_content = mem.read_guest(self._current_sender_id)
        match = re.search(r"TrustScore:\s*(\d+)", guest_content, re.IGNORECASE)
        return int(match.group(1)) if match else 50

    async def execute(
        self,
        target_id: str,
        target_type: str,
        content: str,
        **kwargs: Any,
    ) -> str:
        if not target_id or not target_type or not content:
            return "Error: target_id, target_type, and content are all required."

        if target_type not in ("user", "group"):
            return "Error: target_type must be 'user' or 'group'."

        # Trust score gate
        if not self._current_is_master:
            score = self._get_trust_score()
            if score < self.TRUST_THRESHOLD:
                return (
                    f"Access denied: your TrustScore ({score}) is below the "
                    f"required threshold ({self.TRUST_THRESHOLD}). "
                    "Only trusted users can send cross-session messages."
                )

        if not self._send_callback:
            return "Error: Message sending not configured."

        # Build outbound message with correct conversation_type for routing
        conversation_type = "2" if target_type == "group" else "1"
        msg = OutboundMessage(
            channel="dingtalk",
            chat_id=target_id,
            content=content,
            metadata={"conversation_type": conversation_type},
        )

        try:
            await self._send_callback(msg)
            target_label = "group" if target_type == "group" else "user"
            logger.info(
                "Cross-chat message sent to {} {} by {}",
                target_label, target_id, self._current_sender_id,
            )
        except Exception as e:
            return f"Error sending cross-chat message: {e}"
class ReadRecentMessagesTool(Tool):
    """Read recent messages from a specific DingTalk user or group's session.
    
    Used by the Cron Arbitration engine to verify if a user has replied.
    """

    def __init__(self, workspace: Path):
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "read_recent_messages"

    @property
    def description(self) -> str:
        return (
            "Read the most recent messages from a specific user or group's chat session. "
            "Use this tool to verify stop conditions like 'Check if User X has replied in the last 10 minutes'. "
            "It returns the last N lines of their conversation history, including timestamps and sender names."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target_id": {
                    "type": "string",
                    "description": "The target userId (for private chat) or openConversationId (for group chat)",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of recent message lines to retrieve (default 30, max 100)",
                    "default": 30,
                },
            },
            "required": ["target_id"],
        }

    async def execute(
        self,
        target_id: str,
        lines: int = 30,
        **kwargs: Any,
    ) -> str:
        if not target_id:
            return "Error: target_id is required."

        lines = max(1, min(100, lines))
        session_file = self._workspace / "sessions" / f"dingtalk:{target_id}.md"

        if not session_file.exists():
            return f"No recent chat history found for target '{target_id}' (Session file does not exist)."

        try:
            content = session_file.read_text(encoding="utf-8")
            all_lines = content.splitlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            if not recent_lines:
                return f"Chat history for target '{target_id}' is empty."
                
            history_text = "\n".join(recent_lines)
            return f"Recent chat history for target '{target_id}' (last {len(recent_lines)} lines):\n\n{history_text}"
            
        except Exception as e:
            logger.error("Failed to read session file for target {}: {}", target_id, e)
            return f"Error reading chat history: {e}"

