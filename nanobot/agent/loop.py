"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import re
import time
import weakref
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session, SessionManager
from nanobot.agent.tickets import TicketManager
from nanobot.agent.tools.tickets import EscalateToMasterTool, ResolveTicketTool
from nanobot.agent.tools.cross_chat import SearchContactsTool, SendCrossChatTool

if TYPE_CHECKING:
    from nanobot.config.schema import ChannelsConfig, ExecToolConfig
    from nanobot.cron.service import CronService


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 500

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        reasoning_effort: str | None = None,
        tool_use: bool = True,
        brave_api_key: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig
        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.reasoning_effort = reasoning_effort
        self.tool_use = tool_use
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.ticket_manager = TicketManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=reasoning_effort,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._consolidation_tasks: set[asyncio.Task] = set()  # Strong refs to in-flight tasks
        self._consolidation_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._processing_lock = asyncio.Lock()
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
            path_append=self.exec_config.path_append,
        ))
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

        master_channels = []
        if self.channels_config:
            if hasattr(self.channels_config, "dingtalk") and getattr(self.channels_config, "dingtalk", None):
                dt_cfg = getattr(self.channels_config, "dingtalk")
                if hasattr(dt_cfg, "master_ids") and getattr(dt_cfg, "master_ids", None):
                    for m_id in dt_cfg.master_ids:
                        master_channels.append(("dingtalk", m_id))

        if master_channels:
            self.tools.register(EscalateToMasterTool(
                ticket_manager=self.ticket_manager,
                send_callback=self.bus.publish_outbound,
                master_channels=master_channels
            ))
            
        self.tools.register(ResolveTicketTool(
            ticket_manager=self.ticket_manager,
            send_callback=self.bus.publish_outbound
        ))

        # Cross-session chat tools (available when DingTalk is enabled)
        if self.channels_config and hasattr(self.channels_config, "dingtalk"):
            dt_cfg = getattr(self.channels_config, "dingtalk")
            if dt_cfg and dt_cfg.enabled:
                self.tools.register(SearchContactsTool(workspace=self.workspace))
                self.tools.register(SendCrossChatTool(
                    send_callback=self.bus.publish_outbound,
                    workspace=self.workspace,
                ))

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from nanobot.agent.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except Exception as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "spawn", "cron"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove thinking/reasoning content that models embed in their output.

        Handles:
        - <think>…</think> blocks (DeepSeek-R1, QWQ via some providers, etc.)
        - <thought>…</thought> blocks
        """
        if not text:
            return None
        # Strip common thinking tags
        text = re.sub(r"<think>[\s\S]*?</think>", "", text)
        text = re.sub(r"<thought>[\s\S]*?</thought>", "", text)
        return text.strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    @staticmethod
    def _extract_tool_calls(text: str) -> list:
        """Extract <tool_call> JSON from plain text. Returns list of boxy-style ChoiceDeltaToolCall."""
        import json
        from types import SimpleNamespace
        
        calls = []
        # Find all <tool_call> ... </tool_call> blocks
        matches = re.finditer(r"<tool_call>\s*({[\s\S]*?})\s*</tool_call>", text)
        for i, m in enumerate(matches):
            try:
                data = json.loads(m.group(1))
                if "name" in data:
                    # Map to a structure similar to LiteLLM's tool call object
                    calls.append(SimpleNamespace(
                        id=f"ext-{i}",
                        name=data["name"],
                        arguments=data.get("arguments", {}),
                        function=SimpleNamespace(
                            name=data["name"],
                            arguments=json.dumps(data.get("arguments", {}))
                        )
                    ))
            except Exception:
                continue
        return calls

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop. Returns (final_content, tools_used, messages)."""
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        tool_defs = self.tools.get_definitions() if self.tool_use else None
        tools_disabled = not self.tool_use
        if tools_disabled:
            logger.info("Tool use disabled by config for model {}", self.model)

        while iteration < self.max_iterations:
            iteration += 1

            t0 = time.monotonic()
            logger.info("LLM call #{} starting...{}", iteration, " (no tools)" if tools_disabled else "")
            
            if messages:
                logger.info("▶️ [LLM Input] To Model {}:\n{}", self.model, json.dumps(messages[-1:], ensure_ascii=False, indent=2))
                
            response = await self.provider.chat(
                messages=messages,
                tools=None if tools_disabled else tool_defs,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
            )
            elapsed = time.monotonic() - t0
            logger.info("LLM call #{} returned in {:.1f}s (finish_reason={})", iteration, elapsed, response.finish_reason)

            if response.content:
                logger.info("◀️ [LLM Output] Content:\n{}", response.content)
            if response.has_tool_calls:
                tc_hints = [{"name": t.name, "args": getattr(t, "arguments", {})} for t in response.tool_calls]
                logger.info("◀️ [LLM Output] Tool Calls:\n{}", json.dumps(tc_hints, ensure_ascii=False, indent=2))

            # Auto-fallback: if model doesn't support tools, retry without them
            if (
                response.finish_reason == "error"
                and not tools_disabled
                and iteration == 1
                and any(kw in (response.content or "").lower() for kw in ("unsupported", "tool", "function"))
            ):
                logger.warning("Model {} failed with tool use, retrying without tools", self.model)
                tools_disabled = True
                iteration -= 1
                continue

            # Defensive: Handle models that output tool calls in text (even if finish_reason=stop)
            # or when LiteLLM didn't catch them as structured tool_calls.
            if response.content and "<tool_call>" in response.content:
                logger.info("Detected inline <tool_call> in response content")
                extracted = self._extract_tool_calls(response.content)
                if extracted:
                    # Append extracted calls to any existing ones
                    if not response.tool_calls:
                        response.tool_calls = extracted
                    else:
                        response.tool_calls.extend(extracted)
                    response.has_tool_calls = True
                    # Strip the tool call tags from content so they aren't sent to user
                    response.content = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", response.content).strip()

            if response.has_tool_calls:
                if on_progress:
                    clean = self._strip_think(response.content)
                    if clean:
                        await on_progress(clean)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                clean = self._strip_think(response.content)
                # Don't persist error responses to session history — they can
                # poison the context and cause permanent 400 loops (#1303).
                if response.finish_reason == "error":
                    logger.error("LLM returned error: {}", (clean or "")[:200])
                    final_content = clean or "Sorry, I encountered an error calling the AI model."
                    break
                messages = self.context.add_assistant_message(
                    messages, clean, reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if msg.content.strip().lower() == "/stop":
                await self._handle_stop(msg)
            else:
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(msg.session_key, []).append(task)
                task.add_done_callback(lambda t, k=msg.session_key: self._active_tasks.get(k, []) and self._active_tasks[k].remove(t) if t in self._active_tasks.get(k, []) else None)

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session."""
        tasks = self._active_tasks.pop(msg.session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await self.subagents.cancel_by_session(msg.session_key)
        total = cancelled + sub_cancelled
        content = f"⏹ Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message under the global lock."""
        async with self._processing_lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content="", metadata=msg.metadata or {},
                    ))
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Sorry, I encountered an error.",
                ))

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            history = session.get_history(max_messages=self.memory_window)
            
            is_master = False
            if self.channels_config and getattr(self.channels_config, channel, None):
                channel_cfg = getattr(self.channels_config, channel)
                if hasattr(channel_cfg, "master_ids") and msg.sender_id in channel_cfg.master_ids:
                    is_master = True

            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
                is_master=is_master,
                current_user_id=msg.sender_id
            )
            final_content, _, all_msgs = await self._run_agent_loop(messages)
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        is_master = False
        if self.channels_config and getattr(self.channels_config, msg.channel, None):
            channel_cfg = getattr(self.channels_config, msg.channel)
            if hasattr(channel_cfg, "master_ids") and msg.sender_id in channel_cfg.master_ids:
                is_master = True

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Dynamically record group name for cross-chat search
        conv_type = msg.metadata.get("conversation_type")
        conv_title = msg.metadata.get("conversation_title")
        if conv_type == "2" and conv_title:
            MemoryStore(self.workspace).save_group_info(msg.chat_id, conv_title)

        # Slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())
            self._consolidating.add(session.key)
            try:
                async with lock:
                    snapshot = session.messages[session.last_consolidated:]
                    if snapshot:
                        temp = Session(key=session.key)
                        temp.messages = list(snapshot)
                        if not await self._consolidate_memory(temp, current_user_id=msg.sender_id, is_master=is_master, archive_all=True):
                            return OutboundMessage(
                                channel=msg.channel, chat_id=msg.chat_id,
                                content="Memory archival failed, session not cleared. Please try again.",
                            )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )
            finally:
                self._consolidating.discard(session.key)

            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="New session started.")
        if cmd == "/help":
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="🐈 nanobot commands:\n/new — Start a new conversation\n/stop — Stop the current task\n/help — Show available commands")

        unconsolidated = len(session.messages) - session.last_consolidated
        if (unconsolidated >= self.memory_window and session.key not in self._consolidating):
            self._consolidating.add(session.key)
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())

            async def _consolidate_and_unlock():
                try:
                    async with lock:
                        await self._consolidate_memory(session, current_user_id=msg.sender_id, is_master=is_master)
                finally:
                    self._consolidating.discard(session.key)
                    _task = asyncio.current_task()
                    if _task is not None:
                        self._consolidation_tasks.discard(_task)

            _task = asyncio.create_task(_consolidate_and_unlock())
            self._consolidation_tasks.add(_task)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()
        
        if escalate_tool := self.tools.get("escalate_to_master"):
            if isinstance(escalate_tool, EscalateToMasterTool):
                sender_name = msg.metadata.get("sender_name", "")
                escalate_tool.start_turn(msg.channel, msg.chat_id, msg.sender_id, guest_name=sender_name)

        if cross_chat_tool := self.tools.get("send_cross_chat"):
            if isinstance(cross_chat_tool, SendCrossChatTool):
                cross_chat_tool.set_context(sender_id=msg.sender_id, is_master=is_master)

        history = session.get_history(max_messages=self.memory_window)
        
        # is_master is already calculated above
        
        if not is_master:
            from nanobot.agent.sanitizer import SanitizerAgent
            sanitizer = SanitizerAgent(self.provider, self.model)
            t_san = time.monotonic()
            verdict, sanitizer_msg = await sanitizer.sanitize_input(msg.content, is_master=is_master)
            logger.info("Sanitizer input check took {:.1f}s → {}", time.monotonic() - t_san, verdict)
            if verdict == "BLOCK":
                logger.warning("Input BLOCKED for {}: {}", msg.sender_id, sanitizer_msg)
                return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=sanitizer_msg, metadata=msg.metadata or {})
            elif verdict == "ESCALATE":
                logger.info("Input ESCALATED for {}: {}", msg.sender_id, sanitizer_msg)
                guest_name = msg.metadata.get("sender_name", msg.sender_id)
                # Trigger escalate_to_master programmatically
                if escalate_tool := self.tools.get("escalate_to_master"):
                    if isinstance(escalate_tool, EscalateToMasterTool):
                        await escalate_tool.execute(
                            summary=f"[Sanitizer Escalation] Guest {guest_name} probing: {sanitizer_msg}",
                            pacifier_message=""
                        )
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="这个问题我需要跟老板确认一下才能答复您，请您稍等，我马上帮您跟进。",
                    metadata=msg.metadata or {},
                )

        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
            is_master=is_master,
            current_user_id=msg.sender_id,
            sender_name=msg.metadata.get("sender_name", ""),
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages, on_progress=on_progress or _bus_progress,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        if True: # Always audit, but pass is_master to the auditor
            from nanobot.agent.sanitizer import SanitizerAgent
            sanitizer = SanitizerAgent(self.provider, self.model)
            t_aud = time.monotonic()
            audited_content = await sanitizer.audit_output(final_content, is_master=is_master)
            logger.info("Sanitizer output audit took {:.1f}s", time.monotonic() - t_aud)
            if audited_content != final_content:
                final_content = audited_content
                # Rewrite the last assistant message in internal history so it doesn't remember the leaked version
                if all_msgs and all_msgs[-1]["role"] == "assistant":
                    all_msgs[-1]["content"] = final_content

        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)

        # Ensure guest memory file exists for non-master users on first contact.
        # Fixes: group chat consolidation threshold (memory_window=100) is rarely
        # reached per-user, so guest memory was never created for group @mentions.
        if not is_master and msg.sender_id not in ("Unknown", "user"):
            mem_store = MemoryStore(self.workspace)
            guest_file = mem_store._get_guest_file(msg.sender_id)
            if not guest_file.exists():
                from datetime import datetime as _dt
                sender_name = msg.metadata.get("sender_name", "")
                initial = (
                    f"---\nTrustScore: 50\n---\n"
                    f"## Guest: {sender_name} ({msg.sender_id})\n\n"
                    f"- 首次互动: {_dt.now().strftime('%Y-%m-%d %H:%M')}\n"
                    f"- 来源: {msg.channel}\n"
                )
                mem_store.write_guest(msg.sender_id, initial)
                logger.info("Created initial guest memory for {} ({})", sender_name, msg.sender_id)

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.success("🤖 Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=msg.metadata or {},
        )

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime
        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages — they poison session context
            if role == "tool" and isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
                entry["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                    continue
                if isinstance(content, list):
                    entry["content"] = [
                        {"type": "text", "text": "[image]"} if (
                            c.get("type") == "image_url"
                            and c.get("image_url", {}).get("url", "").startswith("data:image/")
                        ) else c for c in content
                    ]
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def _consolidate_memory(self, session, current_user_id: str = "Unknown", is_master: bool = False, archive_all: bool = False) -> bool:
        """Delegate to MemoryStore.consolidate(). Returns True on success."""
        success = await MemoryStore(self.workspace).consolidate(
            session, self.provider, self.model,
            archive_all=archive_all, memory_window=self.memory_window,
            current_user_id=current_user_id,
            is_master=is_master
        )

        if success and not is_master and current_user_id != "Unknown" and current_user_id != "user":
            async def _background_reflect():
                try:
                    from nanobot.agent.reflection import ReflectionAgent
                    mem_store = MemoryStore(self.workspace)
                    agent = ReflectionAgent(mem_store, self.provider, self.model)
                    alert = await agent.reflect_on_guest(current_user_id)
                    
                    if alert:
                        if self.channels_config and getattr(self.channels_config, 'dingtalk', None):
                            dt_cfg = getattr(self.channels_config, 'dingtalk')
                            if hasattr(dt_cfg, 'master_ids') and getattr(dt_cfg, 'master_ids', None):
                                from nanobot.models import OutboundMessage
                                for m_id in dt_cfg.master_ids:
                                    logger.info("Forwarding reflection alert to master {}", m_id)
                                    await self.bus.publish_outbound(OutboundMessage(
                                        channel="dingtalk", chat_id=m_id,
                                        content=f"⚠️ {alert}"
                                    ))
                except Exception:
                    logger.exception("Background reflection failed")

            _task = asyncio.create_task(_background_reflect())
            if hasattr(self, '_consolidation_tasks'):
                self._consolidation_tasks.add(_task)

        return success

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(msg, session_key=session_key, on_progress=on_progress)
        return response.content if response else ""
