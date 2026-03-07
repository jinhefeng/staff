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
        # 归档逻辑前移：唤醒即执行物理归档，确保后续决策视图干净
        await self._archive_completed_tasks()

        content = self._read_heartbeat_file()
        if not content:
            logger.debug("Heartbeat: HEARTBEAT.md missing or empty")
            return

        # 同步文件头部文案（动态化提示）
        content = self._sync_file_header_with_config(content)

        logger.info("Heartbeat: checking for tasks...")

        try:
            action, task, is_subconscious = await self._decide(content)

            if action != "run":
                logger.info("Heartbeat: OK (nothing to report)")
                await self._check_deferred_retries()
                return

            logger.info("Heartbeat: task found, executing: {}", task)
            
            # Send 'Starting' notification for normal async tasks ONLY
            if self.on_notify and not is_subconscious:
                start_msg = f"⌛ **【心跳任务启动】**\n\n老板，我正开始处理此项异步研发任务：\n> {task}\n\n执行过程中我将保持静默，完成后会即时汇报结果。"
                await self.on_notify(start_msg)

            if self.on_execute:
                response = await self.on_execute(task)
                
                # 无论执行结果如何，只要执行完成了，就将该任务在文件中标记为完成
                self._mark_task_completed(task)
                
                if response and self.on_notify:
                    # Final notification for conclusion (success or failure)
                    if is_subconscious:
                        final_msg = f"✅ **【潜意识反思完成】**\n\n老板，最近的记忆片段已成功归档至 `guests` 记忆池中。\n\n**提纯总结如下：**\n\n{response}"
                    else:
                        final_msg = f"🏁 **【心跳任务完结】**\n\n针对任务：\n> {task}\n\n**我的汇报如下：**\n\n{response}\n\n请您查阅。"
                    
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

    def _mark_task_completed(self, task_desc: str) -> bool:
        """Mark a task as completed in HEARTBEAT.md using a two-tier matching strategy."""
        if not self.heartbeat_file.exists():
            return False

        try:
            content = self.heartbeat_file.read_text(encoding="utf-8")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Try to extract ticket ID from task_desc first to ensure we can resolve it later
            ticket_id = None
            ticket_match = re.search(r"TICKET (TKT-[A-Z0-9]+)", task_desc)
            if ticket_match:
                ticket_id = ticket_match.group(1)

            # Tier 1: Exact Match
            exact_pattern = rf"^- \[ \] \s*{re.escape(task_desc.strip())}\s*$"
            if re.search(exact_pattern, content, re.MULTILINE):
                new_line = f"- [x] {task_desc.strip()} (Done @ {timestamp})"
                new_content = re.sub(exact_pattern, new_line, content, flags=re.MULTILINE)
                self.heartbeat_file.write_text(new_content, encoding="utf-8")
                
                # Trigger physical archive if ticket ID is present
                if ticket_id and self.ticket_manager:
                    logger.info("Heartbeat (Tier 1): triggering physical archive for ticket {}", ticket_id)
                    self.ticket_manager.resolve_ticket(ticket_id)
                return True

            # Tier 2: Ticket ID Match (Stable Anchor)
            if ticket_id:
                ticket_pattern = rf"^- \[ \] .*?{re.escape(ticket_id)}.*?$"
                match = re.search(ticket_pattern, content, re.MULTILINE)
                if match:
                    original_line = match.group(0)
                    if original_line.startswith("- [ ]"):
                        new_line = original_line.replace("- [ ]", "- [x]", 1)
                        if "(Done @" not in new_line:
                            new_line += f" (Done @ {timestamp})"
                        
                        new_content = content.replace(original_line, new_line, 1)
                        self.heartbeat_file.write_text(new_content, encoding="utf-8")
                        
                        if self.ticket_manager:
                            logger.info("Heartbeat (Tier 2): triggering physical archive for ticket {}", ticket_id)
                            self.ticket_manager.resolve_ticket(ticket_id)
                        return True

            logger.warning("Heartbeat: could not find task line to mark in file: {}", task_desc)
            return False
        except Exception as e:
            logger.error("Failed to mark task as completed: {}", e)
            return False

    def _sync_file_header_with_config(self, content: str) -> str:
        """Ensures the minutes mentioned in the header match current intervalS."""
        minutes = str(self.interval_s // 60)
        changed = False

        # Match "你的底层引擎每 XX 分钟会唤醒你一次"
        cn_pattern = r"(你的底层引擎每 )(\d+)( 分钟会唤醒你一次)"
        if (m := re.search(cn_pattern, content)):
            if m.group(2) != minutes:
                content = re.sub(cn_pattern, rf"\1{minutes}\3", content)
                changed = True

        # Match "This file is checked every XX minutes"
        en_pattern = r"(This file is checked every )(\d+)( minutes)"
        if (m := re.search(en_pattern, content)):
            if m.group(2) != minutes:
                content = re.sub(en_pattern, rf"\1{minutes}\3", content)
                changed = True

        if changed:
            try:
                self.heartbeat_file.write_text(content, encoding="utf-8")
                logger.info("Heartbeat: Synced file header instruction with config ({} minutes)", minutes)
            except Exception as e:
                logger.error("Failed to sync HEARTBEAT.md header: {}", e)

        return content

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

    async def _archive_completed_tasks(self) -> None:
        """Physical archiving: move [x] lines from anywhere into the ## Completed section."""
        if not self.heartbeat_file.exists():
            return
        
        try:
            content_lines = self.heartbeat_file.read_text(encoding="utf-8").splitlines()
            active_tasks = []
            completed_tasks = []
            other_content = []
            
            # 识别主要区域
            state = "header" # header, active, completed
            for line in content_lines:
                stripped = line.strip()
                if stripped.startswith("## Active Tasks"):
                    state = "active"
                    other_content.append(line)
                    continue
                elif stripped.startswith("## Completed"):
                    state = "completed"
                    other_content.append(line)
                    continue
                elif stripped.startswith("---") or (stripped == "" and state == "header"):
                    other_content.append(line)
                    continue
                
                # 任务行识别
                if stripped.startswith("- [ ]") or stripped.startswith("- [x]"):
                    if stripped.startswith("- [x]"):
                        completed_tasks.append(line)
                    else:
                        active_tasks.append(line)
                else:
                    other_content.append(line)

            # 只有当有新完成的任务时才写回文件
            if not completed_tasks:
                return

            # 构建新文件内容
            new_lines = []
            # 1. 写入 Header 和 Active 区域
            found_active = False
            found_completed = False
            
            for line in other_content:
                new_lines.append(line)
                if "## Active Tasks" in line:
                    found_active = True
                    # 插入活跃任务
                    for task in active_tasks:
                        new_lines.append(task)
                elif "## Completed" in line:
                    found_completed = True
                    # 插入已完成任务
                    for task in completed_tasks:
                        new_lines.append(task)

            self.heartbeat_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            logger.info("Archived {} completed tasks in HEARTBEAT.md", len(completed_tasks))
        except Exception as e:
            logger.error("Failed to archive completed tasks: {}", e)

    async def trigger_now(self) -> str | None:
        """Manually trigger a heartbeat."""
        content = self._read_heartbeat_file()
        if not content:
            return None
        action, tasks, _ = await self._decide(content)
        if action != "run" or not self.on_execute:
            return None
        return await self.on_execute(tasks)
