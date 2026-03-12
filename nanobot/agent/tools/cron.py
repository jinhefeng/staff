"""Cron tool for scheduling reminders and tasks."""

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.cron.service import CronService
from nanobot.cron.types import CronSchedule


class CronTool(Tool):
    """Tool to schedule reminders and recurring tasks."""
    
    def __init__(self, cron_service: CronService, available_tools: list[str] | None = None):
        self._cron = cron_service
        self._available_tools = available_tools or []
        self._channel = ""
        self._chat_id = ""
    
    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current session context for delivery."""
        self._channel = channel
        self._chat_id = chat_id
    
    @property
    def name(self) -> str:
        return "cron"
    
    @property
    def description(self) -> str:
        return (
            "MANDATORY: Call this tool for ANY scheduled tasks, reminders, or alarms.\n"
            "CRITICAL: This is an Autonomous Cron Engine. For RECURRING tasks, you MUST define a `stop_condition` "
            "and explicitly declare all `required_tools` you will need to evaluate that condition when you wake up. "
            "If you lack the required tools to verify the stop condition, the schedule will be REJECTED. "
            "Example: to stop when a user replies, you need a generic tool like `read_recent_messages`. If we don't have it, do not create."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "remove"],
                    "description": "Action to perform"
                },
                "task_content": {
                    "type": "string",
                    "description": "What to do when triggered (e.g. 'Send a message to user X asking Y')"
                },
                "stop_condition": {
                    "type": "string",
                    "description": "Natural language condition evaluated to stop this recurring task (e.g. 'Check if user X has replied in the last 10 mins')"
                },
                "required_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of tool names needed to evaluate the stop_condition and execute the task (e.g. ['send_cross_chat'])"
                },
                "every_seconds": {
                    "type": "integer",
                    "description": "Interval in seconds (for recurring tasks)"
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression like '0 9 * * *' (for scheduled tasks)"
                },
                "tz": {
                    "type": "string",
                    "description": "IANA timezone for cron expressions (e.g. 'America/Vancouver')"
                },
                "at": {
                    "type": "string",
                    "description": "ISO datetime for one-time execution (e.g. '2026-02-12T10:30:00')"
                },
                "delay_seconds": {
                    "type": "integer",
                    "description": "Delay before execution in seconds (for one-time future tasks like 'in 2 minutes' -> 120)"
                },
                "job_id": {
                    "type": "string",
                    "description": "Job ID (for remove)"
                }
            },
            "required": ["action"]
        }
    
    async def execute(
        self,
        action: str,
        task_content: str = "",
        stop_condition: str | None = None,
        required_tools: list[str] | None = None,
        every_seconds: int | None = None,
        cron_expr: str | None = None,
        tz: str | None = None,
        at: str | None = None,
        delay_seconds: int | None = None,
        job_id: str | None = None,
        **kwargs: Any
    ) -> str:
        if action == "add":
            return self._add_job(task_content, stop_condition, required_tools, every_seconds, cron_expr, tz, at, delay_seconds)
        elif action == "list":
            return self._list_jobs()
        elif action == "remove":
            return self._remove_job(job_id)
        return f"Unknown action: {action}"
    
    def _add_job(
        self,
        task_content: str,
        stop_condition: str | None,
        required_tools: list[str] | None,
        every_seconds: int | None,
        cron_expr: str | None,
        tz: str | None,
        at: str | None,
        delay_seconds: int | None = None,
    ) -> str:
        if not task_content:
            return "Error: task_content is required for add"
        
        # Pre-flight Validation
        required_tools = required_tools or []
        missing_tools = [t for t in required_tools if t not in self._available_tools]
        if missing_tools:
            return (
                f"Error: PRE-FLIGHT VALIDATION FAILED! You requested tools that are not currently mounted in the system: {missing_tools}. "
                "You do NOT have the capability to independently evaluate your stop condition or execute this task. "
                "Please adjust your plan, remove the dependency on these tools, or ask the user to mount the corresponding plugins first."
            )
        if not self._channel or not self._chat_id:
            return "Error: no session context (channel/chat_id)"
        if tz and not cron_expr:
            return "Error: tz can only be used with cron_expr"
        if tz:
            from zoneinfo import ZoneInfo
            try:
                ZoneInfo(tz)
            except (KeyError, Exception):
                return f"Error: unknown timezone '{tz}'"
        
        # Build schedule
        delete_after = False
        if every_seconds:
            schedule = CronSchedule(kind="every", every_ms=every_seconds * 1000)
        elif cron_expr:
            schedule = CronSchedule(kind="cron", expr=cron_expr, tz=tz)
        elif delay_seconds:
            from datetime import datetime, timedelta
            at_ms = int((datetime.now() + timedelta(seconds=delay_seconds)).timestamp() * 1000)
            schedule = CronSchedule(kind="at", at_ms=at_ms)
            delete_after = True
        elif at:
            from datetime import datetime
            dt = datetime.fromisoformat(at)
            at_ms = int(dt.timestamp() * 1000)
            schedule = CronSchedule(kind="at", at_ms=at_ms)
            delete_after = True
        else:
            return "Error: either every_seconds, cron_expr, delay_seconds, or at is required"
        
        job = self._cron.add_job(
            name=task_content[:30],
            schedule=schedule,
            task_content=task_content,
            stop_condition=stop_condition,
            required_tools=required_tools,
            deliver=True,
            channel=self._channel,
            to=self._chat_id,
            delete_after_run=delete_after,
        )
        return f"Created job '{job.name}' (id: {job.id})"
    
    def _list_jobs(self) -> str:
        jobs = self._cron.list_jobs()
        if not jobs:
            return "No scheduled jobs."
        lines = [f"- {j.name} (id: {j.id}, {j.schedule.kind})" for j in jobs]
        return "Scheduled jobs:\n" + "\n".join(lines)
    
    def _remove_job(self, job_id: str | None) -> str:
        if not job_id:
            return "Error: job_id is required for remove"
        if self._cron.remove_job(job_id):
            return f"Removed job {job_id}"
        return f"Job {job_id} not found"
