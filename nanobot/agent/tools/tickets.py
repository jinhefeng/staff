"""Tools for escalating issues to the Master via async tickets."""

from typing import Any
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
        "Use this tool when you are asked an sensitive, secure, or private question that you "
        "do not have permission or certainty to answer, OR when a guest asks for the Master. "
        "This will asynchronously forward the question to the Master for human approval, "
        "and provide an initial placating response to the user."
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
                    "description": "A concise summary of what the guest is asking for so the Master can make a decision.",
                },
                "pacifier_message": {
                    "type": "string",
                    "description": "What to reply directly to the guest right now, politely explaining that you need to check with the boss. E.g., 'I will need to ask the boss about this. I'll get back to you shortly.'",
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
        forward_msg = f"🎟️ **TICKET {ticket_id}** (from {guest_display})\n\n{summary}\n\n*Reply mentioning the ticket ID to resolve this.*"
        
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
    """Tool for the Master to resolve a pending async ticket."""

    name = "resolve_ticket"
    description = (
        "Use this tool when you (acting on behalf of the Master) want to answer a pending ticket "
        "and send a message back to the guest who asked the question."
    )

    def __init__(self, ticket_manager: TicketManager, send_callback: Any):
        self.ticket_manager = ticket_manager
        self.send_callback = send_callback

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ticket_id": {
                    "type": "string",
                    "description": "The exact ticket ID (e.g., TKT-1A2B3C4D)."
                },
                "message_to_guest": {
                    "type": "string",
                    "description": "The final message to send back to the guest, written in an appropriate tone."
                }
            },
            "required": ["ticket_id", "message_to_guest"]
        }

    async def execute(self, ticket_id: str, message_to_guest: str) -> str:
        ticket = self.ticket_manager.resolve_ticket(ticket_id)
        if not ticket:
            return f"Error: Ticket {ticket_id} not found or already resolved."

        # Forward the message back to the guest asynchronously
        asyncio.create_task(
            self.send_callback(OutboundMessage(
                channel=ticket["guest_channel"],
                chat_id=ticket["guest_chat_id"],
                content=message_to_guest
            ))
        )

        return f"Successfully resolved ticket {ticket_id} and dispatched message to guest."
