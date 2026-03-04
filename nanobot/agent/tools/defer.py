from typing import Any
from nanobot.agent.tools.base import Tool
from nanobot.agent.tickets import TicketManager
from loguru import logger
import asyncio

class DeferTaskTool(Tool):
    """Tool to officially defer a task to the background and log it as a ticket."""

    name = "defer_to_background"
    description = (
        "CRITICAL ANTI-LIP-SERVICE TOOL. Use this tool IMMEDIATELY ANY TIME you tell the user you will "
        "'fix a skill later', 'look for an alternative', 'research something', or do ANY asynchronous background work. "
        "DO NOT just promise to do it in text. You MUST use this tool to officially log the promise as a background task. "
        "This tool creates a tracked background ticket to ensure you don't forget."
    )

    def __init__(self, ticket_manager: TicketManager):
        self.ticket_manager = ticket_manager
        self._current_guest_channel = ""
        self._current_guest_chat_id = ""
        self._current_guest_id = ""
        self._current_guest_name = ""

    def start_turn(self, channel: str, chat_id: str, guest_id: str, guest_name: str = "") -> None:
        self._current_guest_channel = channel
        self._current_guest_chat_id = chat_id
        self._current_guest_id = guest_id
        self._current_guest_name = guest_name or guest_id

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "What exactly you are promising to do in the background (e.g. 'Fix the Yahoo Finance stock API issue by finding a new source')",
                },
                "reply_to_user": {
                    "type": "string",
                    "description": "What you want to say to the user right now (e.g. 'I will find a new data source and update the skill for you.')",
                },
            },
            "required": ["task_description", "reply_to_user"],
        }

    async def execute(self, task_description: str, reply_to_user: str) -> str:
        guest_display = self._current_guest_name or self._current_guest_id
        ticket_id = self.ticket_manager.create_ticket(
            guest_id=self._current_guest_id,
            channel=self._current_guest_channel,
            chat_id=self._current_guest_chat_id,
            content=f"[DEFERRED TASK] {task_description}",
            guest_name=self._current_guest_name,
        )
        logger.info(f"Task deferred as ticket {ticket_id} for user {guest_display}")
        return f"System logged the deferred task as Ticket {ticket_id}. Feel free to output the following message to the user: {reply_to_user}"
