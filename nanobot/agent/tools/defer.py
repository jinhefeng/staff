"""Tool for deferring tasks to the background with Master approval."""

from typing import Any
from nanobot.agent.tools.base import Tool
from nanobot.agent.tickets import TicketManager
from nanobot.bus.events import OutboundMessage
from loguru import logger
import asyncio


class DeferTaskTool(Tool):
    """Tool to officially defer a task to the background via Master-approved ticket.

    Flow:
    1. Creates a ticket in active_tickets.json (status=pending)
    2. Notifies Master via their configured channels
    3. Master approves → ticket moves to HEARTBEAT.md for execution
    """

    name = "defer_to_background"
    description = (
        "【防敷衍核心工具】当你准备向用户承诺'稍后修复技能'、'去找替代方案'、'研究一下'等任何异步后台工作时，"
        "你【必须】立即使用此工具，将承诺正式登记为后台工单。"
        "禁止只在文字中做出承诺而不调用此工具。"
        "此工具会创建工单并通知老板审批，老板批准后任务才会进入执行队列。"
    )

    def __init__(self, ticket_manager: TicketManager, send_callback: Any, master_channels: list[tuple[str, str]]):
        self.ticket_manager = ticket_manager
        self.send_callback = send_callback
        self.master_channels = master_channels
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
                    "description": "【必须使用中文】用中文描述你承诺要在后台完成的具体任务。禁止使用英文。例如：'修复雅虎财经股票API，寻找新的数据源'。",
                },
                "reply_to_user": {
                    "type": "string",
                    "description": "【必须使用中文】你现在想对用户说的安抚回复。例如：'我会找新的数据源来更新这个技能'。",
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
        logger.info("Deferred task ticket {} created for user {}", ticket_id, guest_display)

        # Notify Master for approval
        notify_msg = (
            f"🔧 **【延期任务申请】 {ticket_id}**\n\n"
            f"来自: {guest_display}\n"
            f"任务: {task_description}\n\n"
            f"*请回复包含工单号以批准此任务进入执行队列。*"
        )
        for ch, ch_id in self.master_channels:
            logger.info("Notifying Master {}/{} about deferred task {}", ch, ch_id, ticket_id)
            asyncio.create_task(
                self.send_callback(OutboundMessage(
                    channel=ch, chat_id=ch_id, content=notify_msg
                ))
            )

        return (
            f"Deferred task registered as Ticket {ticket_id} and sent to Master for approval. "
            f"The task will enter the execution queue only after Master approves. "
            f"Output to user: {reply_to_user}"
        )
