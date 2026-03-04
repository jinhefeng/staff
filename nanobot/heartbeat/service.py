"""Heartbeat service - periodic agent wake-up to check for tasks.

Enhanced with Plan E: after executing deferred tasks, checks whether the
corresponding tickets were resolved.  If a ticket survives N heartbeat cycles
without resolution, the service escalates it to the Master.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from datetime import datetime, timedelta
from loguru import logger

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.agent.tickets import TicketManager

_MAX_RETRIES = 3  # After this many heartbeat cycles, escalate to Master

_HEARTBEAT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "heartbeat",
            "description": "Report heartbeat decision after reviewing tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["skip", "run"],
                        "description": "skip = nothing to do, run = process ONE active task",
                    },
                    "task": {
                        "type": "string",
                        "description": "The description of the FIRST pending task (marked with [ ]). DO NOT summarize multiple tasks.",
                    },
                    "is_subconscious": {
                        "type": "boolean",
                        "description": "Set to true if this is for the subconscious consolidation when idle.",
                    }
                },
                "required": ["action"],
            },
        },
    }
]


class HeartbeatService:
    """
    Periodic heartbeat service that wakes the agent to check for tasks.

    Phase 1 (decision): reads HEARTBEAT.md and asks the LLM — via a virtual
    tool call — whether there are active tasks.  This avoids free-text parsing
    and the unreliable HEARTBEAT_OK token.

    Phase 2 (execution): only triggered when Phase 1 returns ``run``.  The
    ``on_execute`` callback runs the task through the full agent loop and
    returns the result to deliver.

    Phase 3 (retry check): after execution, checks approved deferred tickets.
    If a ticket is still unresolved after N cycles, escalates to Master.
    """

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        on_execute: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        on_notify: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        ticket_manager: TicketManager | None = None,
        session_manager: Any | None = None,  # Add session_manager
        interval_s: int = 30 * 60,
        enabled: bool = True,
    ):
        self.workspace = workspace
        self.provider = provider
        self.model = model
        self.on_execute = on_execute
        self.on_notify = on_notify
        self.ticket_manager = ticket_manager
        self.session_manager = session_manager
        self.interval_s = interval_s
        self.enabled = enabled
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_idle_notify_time: datetime | None = None

    @property
    def heartbeat_file(self) -> Path:
        return self.workspace / "HEARTBEAT.md"

    def _read_heartbeat_file(self) -> str | None:
        if self.heartbeat_file.exists():
            try:
                return self.heartbeat_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    async def _decide(self, content: str) -> tuple[str, str, bool]:
        """Phase 1: ask LLM to decide skip/run via virtual tool call.

        Returns (action, task, is_subconscious).
        """
        response = await self.provider.chat(
            messages=[
                {"role": "system", "content": (
                    "You are a heartbeat agent. Review HEARTBEAT.md and report your decision.\n"
                    "STRATEGY: Only pick the FIRST task marked with '[ ]'. Skip if none found.\n"
                    "If idle, initiate subconscious reflection."
                )},
                {"role": "user", "content": content},
            ],
            tools=_HEARTBEAT_TOOL,
            model=self.model,
        )

        if not response.has_tool_calls:
            return "skip", "", False

        args = response.tool_calls[0].arguments
        return args.get("action", "skip"), args.get("task", ""), args.get("is_subconscious", False)

    async def start(self) -> None:
        """Start the heartbeat service."""
        if not self.enabled:
            logger.info("Heartbeat disabled")
            return
        if self._running:
            logger.warning("Heartbeat already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Heartbeat started (every {}s)", self.interval_s)

    def stop(self) -> None:
        """Stop the heartbeat service."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Heartbeat error: {}", e)

    async def _tick(self) -> None:
        """Execute a single heartbeat tick."""
        content = self._read_heartbeat_file()
        if not content:
            logger.debug("Heartbeat: HEARTBEAT.md missing or empty")
            return

        logger.info("Heartbeat: checking for tasks...")

        try:
            action, task, is_subconscious = await self._decide(content)

            if action != "run":
                logger.info("Heartbeat: OK (nothing to report)")
                await self._check_deferred_retries()
                return

            logger.info("Heartbeat: task found, executing: {}", task)
            
            # Send 'Starting' notification (including subconscious)
            if self.on_notify:
                if is_subconscious:
                    start_msg = "🧠 **【潜意识反思启动】**\n\n老板，当前处于闲暇期，我正开始整理最近的消息记录，固化您的偏好与客体记忆。内容说明内容说明。数据内容说明。"
                else:
                    start_msg = f"⌛ **【心跳任务启动】**\n\n老板，我正开始处理此项异步研发任务：\n> {task}\n\n执行过程中我将保持静默，完成后会即时汇报结果。内容说明内容说明。数据内容说明。"
                await self.on_notify(start_msg)

            if self.on_execute:
                response = await self.on_execute(task)
                if response and self.on_notify:
                    # Final notification for conclusion (success or failure)
                    if is_subconscious:
                        final_msg = "✅ **【潜意识反思完成】**\n\n老板，最近的记忆片段已成功归档至 `guests` 记忆池中。内容说明内容说明。数据内容说明。"
                    else:
                        final_msg = f"🏁 **【心跳任务完结】**\n\n针对任务：\n> {task}\n\n**我的汇报如下：**\n\n{response}\n\n请您查阅。内容说明内容说明。数据内容说明。"
                    
                    logger.info("Heartbeat: completed, delivering response")
                    await self.on_notify(final_msg)

            # Phase 3: Check deferred ticket retry status
            await self._check_deferred_retries()
            
            # Phase 4: Check for idle period ticket summary (9:00 - 21:00)
            await self._check_idle_period_tickets()

        except Exception:
            logger.exception("Heartbeat execution failed")

    async def _check_deferred_retries(self) -> None:
        """Phase 3 (Plan E): Check approved deferred tickets and bump retry counters.

        If a ticket has been in 'approved' status for more than _MAX_RETRIES
        heartbeat cycles without being resolved, escalate to Master.
        """
        if not self.ticket_manager:
            return

        approved = self.ticket_manager.get_approved_deferred_tickets()
        if not approved:
            return

        for ticket in approved:
            ticket_id = ticket["ticket_id"]
            retries = self.ticket_manager.increment_heartbeat_retries(ticket_id)
            logger.info("Deferred ticket {} retry count: {}/{}", ticket_id, retries, _MAX_RETRIES)

            if retries >= _MAX_RETRIES:
                task_desc = ticket.get("content", "").replace("[DEFERRED TASK] ", "", 1)
                escalation_msg = (
                    f"⚠️ **【延期任务超时】 {ticket_id}**\n\n"
                    f"任务: {task_desc}\n"
                    f"已经过 {retries} 个 Heartbeat 周期（约 {retries * self.interval_s // 60} 分钟）仍未完成。\n\n"
                    f"请确认是否需要人工介入，或回复包含工单号以重置重试次数。"
                )
                logger.warning("Deferred ticket {} exceeded max retries, escalating to Master", ticket_id)

                if self.on_notify:
                    await self.on_notify(escalation_msg)

                # Also clean it from HEARTBEAT.md to avoid repeated execution attempts
                self._remove_ticket_from_heartbeat(ticket_id)

                # Resolve and archive the failed ticket
                self.ticket_manager.resolve_ticket(ticket_id)

    async def _check_idle_period_tickets(self) -> None:
        """Phase 4: Periodic idle check (9:00 - 21:00, 3h silence).
        
        If Master has been silent for > 3 hours and it's within the day window,
        send a gentle summary of active tickets.
        """
        if not self.session_manager or not self.ticket_manager or not self.on_notify:
            return

        # 1. Time window: 9:00 - 21:00
        now = datetime.now()
        if not (9 <= now.hour < 21):
            return

        # 2. Prevent spam: only notify once every 12 hours (or similar) of idle
        if self._last_idle_notify_time and (now - self._last_idle_notify_time) < timedelta(hours=6):
            return

        # 3. Check silence: > 3 hours since last updated session
        sessions = self.session_manager.list_sessions()
        if not sessions:
            return
            
        # Find the most recently updated session
        last_updated_str = sessions[0].get("updated_at")
        if not last_updated_str:
            return
            
        last_updated = datetime.fromisoformat(last_updated_str)
        if (now - last_updated) < timedelta(hours=3):
            return

        # 4. Check for active tickets
        # Note: self.ticket_manager.tickets is a dict of active tickets
        active_tickets = self.ticket_manager.tickets
        if not active_tickets:
            return

        # 5. Send summary
        count = len(active_tickets)
        summary = "\n".join([f"- **{tk}**: {meta.get('content', '')[:50]}..." for tk, meta in list(active_tickets.items())[:5]])
        if count > 5:
            summary += f"\n- ...以及另外 {count - 5} 个工单"

        msg = (
            f"📋 **【工单待办巡检】**\n\n"
            f"老板，我留意到您已休息一段时间了。目前系统中还有 **{count}** 个未完成工单：\n\n"
            f"{summary}\n\n"
            f"如果您现在有空，可以告诉我需要加急处理哪一个。内容说明。数据内容说明。"
        )
        
        logger.info("Heartbeat: idle silence detected, sending ticket summary")
        await self.on_notify(msg)
        self._last_idle_notify_time = now

    def _remove_ticket_from_heartbeat(self, ticket_id: str) -> None:
        """Remove a specific ticket line from HEARTBEAT.md."""
        try:
            content = self.heartbeat_file.read_text(encoding="utf-8")
            # Match lines like: - [ ] [TICKET TKT-xxx] ... or - [x] [TICKET TKT-xxx] ...
            pattern = rf"^- \[[ x]\] \[TICKET {re.escape(ticket_id)}\].*$\n?"
            new_content = re.sub(pattern, "", content, flags=re.MULTILINE)
            self.heartbeat_file.write_text(new_content, encoding="utf-8")
            logger.info("Removed ticket {} from HEARTBEAT.md", ticket_id)
        except Exception:
            logger.exception("Failed to clean HEARTBEAT.md for ticket {}", ticket_id)

    async def trigger_now(self) -> str | None:
        """Manually trigger a heartbeat."""
        content = self._read_heartbeat_file()
        if not content:
            return None
        action, tasks = await self._decide(content)
        if action != "run" or not self.on_execute:
            return None
        return await self.on_execute(tasks)
