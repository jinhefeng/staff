"""Tools for escalating issues to the Master via async tickets."""

from typing import Any
from pathlib import Path
from nanobot.agent.tools.base import Tool
from nanobot.agent.tickets import TicketManager
from nanobot.bus.events import OutboundMessage
from loguru import logger
from datetime import datetime
import asyncio

class EscalateToMasterTool(Tool):
    """Tool to escalate a request to the Master user."""

    name = "escalate_to_master"
    description = (
        "当你被问到敏感、安全或隐私问题且你无权限或无把握回答时使用此工具，"
        "或当访客要求联系老板（金总/主人）时使用。"
        "此工具会异步将问题转发给老板审批，并立即给访客一个安抚性回复。"
    )

    def __init__(self, ticket_manager: TicketManager, send_callback: Any, master_channels: list[tuple[str, str]]):
        """
        master_channels: list of (channel, chat_id) where the Master receives notifications.
        send_callback: async function(OutboundMessage)
        """
        self.ticket_manager = ticket_manager
        self.send_callback = send_callback
        self.master_channels = master_channels
        self._current_guest_channel = ""
        self._current_guest_chat_id = ""
        self._current_guest_id = ""
        self._current_guest_name = ""

    def start_turn(self, channel: str, chat_id: str, guest_id: str, guest_name: str = "") -> None:
        """Call this before each run loop to set context."""
        self._current_guest_channel = channel
        self._current_guest_chat_id = chat_id
        self._current_guest_id = guest_id
        self._current_guest_name = guest_name or guest_id

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "用中文简要概括访客的诉求，供老板做决策。【必须】与访客使用的语言保持一致（访客说中文就写中文，说英文就写英文）。",
                },
                "pacifier_message": {
                    "type": "string",
                    "description": "立即回复给访客的安抚话术，礼貌说明需要跟老板确认。例如：'我已经将您的问题转交，请稍等'。【必须】与访客使用的语言一致。",
                },
            },
            "required": ["summary", "pacifier_message"],
        }

    async def execute(self, summary: str, pacifier_message: str) -> str:
        if not self._current_guest_id:
            return "Error: Ticket context not set."
            
        # 1. Create ticket
        guest_display = self._current_guest_name or self._current_guest_id
        ticket_id = self.ticket_manager.create_ticket(
            guest_id=self._current_guest_id,
            channel=self._current_guest_channel,
            chat_id=self._current_guest_chat_id,
            content=summary,
            guest_name=self._current_guest_name,
        )

        # 2. Forward to Master
        forward_msg = f"🎟️ **【工单提醒】 {ticket_id}** (来自 {guest_display})\n\n{summary}\n\n*请回复包含工单号以处理此请求。*"
        
        for ch, ch_id in self.master_channels:
            logger.info("Escalating ticket {} to master {}/{}", ticket_id, ch, ch_id)
            asyncio.create_task(
                self.send_callback(OutboundMessage(
                    channel=ch, chat_id=ch_id, content=forward_msg
                ))
            )

        # 3. Inform the agent of success and ask it to output the pacifier
        return f"Ticket {ticket_id} created and forwarded to Master. Please use `{pacifier_message}` as your final output to the user."

class ResolveTicketTool(Tool):
    """Tool for the Master to resolve or approve a pending async ticket."""

    name = "resolve_ticket"
    description = (
        "当你（代表老板）要回复一个待处理工单并向访客发送消息时使用此工具。"
        "对于延期任务工单（内容以'[DEFERRED TASK]'开头），此工具会【批准】该任务"
        "并将其加入 HEARTBEAT.md 执行队列，而不是直接关闭工单。"
    )

    def __init__(self, ticket_manager: TicketManager, send_callback: Any, workspace: Path):
        self.ticket_manager = ticket_manager
        self.send_callback = send_callback
        self.workspace = workspace

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "工单的精确ID（例如 TKT-1A2B3C4D）。"
                },
                "message_to_guest": {
                    "type": "string",
                    "description": "回复给访客的最终消息，语气得体。【必须】与访客使用的语言一致。"
                }
            },
            "required": ["ticket_id", "message_to_guest"]
        }

    async def execute(self, ticket_id: str, message_to_guest: str) -> str:
        # Check if ticket exists first
        ticket = self.ticket_manager.tickets.get(ticket_id)
        if not ticket:
            return f"Error: Ticket {ticket_id} not found or already resolved."

        content = ticket.get("content", "")

        # --- Branch: DEFERRED TASK → approve + write to HEARTBEAT ---
        if content.startswith("[DEFERRED TASK]"):
            task_desc = content.replace("[DEFERRED TASK] ", "", 1)
            approved = self.ticket_manager.approve_ticket(ticket_id)
            if not approved:
                return f"Error: Could not approve ticket {ticket_id}."

            # Write to HEARTBEAT.md so HeartbeatService picks it up
            heartbeat_file = self.workspace / "HEARTBEAT.md"
            try:
                with open(heartbeat_file, "a", encoding="utf-8") as f:
                    f.write(f"\n- [ ] [TICKET {ticket_id}] {task_desc}\n")
                logger.info("Approved deferred task {} and appended to HEARTBEAT.md", ticket_id)
            except Exception as e:
                logger.error("Failed to append deferred task to HEARTBEAT.md: {}", e)

            # Notify the requester
            guest_id = ticket.get("guest_id", "")
            guest_channel = ticket.get("guest_channel", "")
            if guest_id and guest_channel and message_to_guest:
                asyncio.create_task(
                    self.send_callback(OutboundMessage(
                        channel=guest_channel,
                        chat_id=guest_id,
                        content=message_to_guest
                    ))
                )

            return (
                f"Deferred task {ticket_id} approved by Master and added to HEARTBEAT.md execution queue. "
                f"The HeartbeatService will execute it in the next cycle."
            )

        # --- Branch: Normal escalation ticket → resolve + reply ---
        resolved = self.ticket_manager.resolve_ticket(ticket_id)
        if not resolved:
            return f"Error: Ticket {ticket_id} not found or already resolved."

        asyncio.create_task(
            self.send_callback(OutboundMessage(
                channel=resolved["guest_channel"],
                chat_id=resolved["guest_id"],
                content=message_to_guest
            ))
        )

        return f"Successfully resolved ticket {ticket_id} and dispatched message to guest."
