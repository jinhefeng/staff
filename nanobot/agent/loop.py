"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import copy
import json
import re
import time
import weakref
from datetime import datetime
# ... [rest of imports]
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
from nanobot.agent.tools.memory import MemorizeFactTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.utils.helpers import ensure_dir
from nanobot.session.manager import Session, SessionManager
from nanobot.agent.tickets import TicketManager
from nanobot.agent.tools.tickets import EscalateToMasterTool, ResolveTicketTool
from nanobot.agent.tools.cross_chat import SearchContactsTool, SendCrossChatTool, ReadRecentMessagesTool

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
        agent_name: str = "nanobot",
        session_max_messages: int = 2000,
        session_clear_to_size: int = 1000,
        session_background_max_messages: int = 100,
        session_background_clear_to_size: int = 50,
        session_background_cleanup_days: int = 15,
        session_safe_buffer: int = 30,
        debug_context: bool = False,
        pre_process_hook: Callable[[InboundMessage], Awaitable[None]] | None = None,
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
        self.session_max_messages = session_max_messages
        self.session_clear_to_size = session_clear_to_size
        self.session_background_max_messages = session_background_max_messages
        self.session_background_clear_to_size = session_background_clear_to_size
        self.session_background_cleanup_days = session_background_cleanup_days
        self.session_safe_buffer = session_safe_buffer
        self.debug_context = debug_context
        self._pre_process_hook = pre_process_hook

        self.sessions = session_manager or SessionManager(workspace)
        self.raw_history_dir = ensure_dir(self.workspace / "sessions" / "raw_history")
        self.ticket_manager = TicketManager(workspace)
        self.context = ContextBuilder(workspace, agent_name=agent_name, ticket_manager=self.ticket_manager)
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
        self._session_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self.memory_store = MemoryStore(workspace)
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
        
        # staff-memory-expert registration
        from workspace.skills.staff_memory_expert.logic import SearchChatHistoryTool, QueryGlobalKnowledgeTool, ReadFullProfileTool, ConsolidateMemoryTool
        self.tools.register(SearchChatHistoryTool(workspace=self.workspace))
        self.tools.register(QueryGlobalKnowledgeTool(workspace=self.workspace))
        self.tools.register(ReadFullProfileTool(workspace=self.workspace))
        self.tools.register(ConsolidateMemoryTool(workspace=self.workspace))

        self.tools.register(MemorizeFactTool(workspace=self.workspace))
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        # Cross-session chat tools (available when DingTalk is enabled)
        if self.channels_config and hasattr(self.channels_config, "dingtalk"):
            dt_cfg = getattr(self.channels_config, "dingtalk")
            if dt_cfg and dt_cfg.enabled:
                self.tools.register(SearchContactsTool(workspace=self.workspace))
                self.tools.register(SendCrossChatTool(
                    send_callback=self.bus.publish_outbound,
                    workspace=self.workspace,
                ))
                self.tools.register(ReadRecentMessagesTool(workspace=self.workspace))

        if self.cron_service:
            self.tools.register(CronTool(self.cron_service, available_tools=self.tools.tool_names))

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
            send_callback=self.bus.publish_outbound,
            workspace=self.workspace,
        ))
        
        from nanobot.agent.tools.defer import DeferTaskTool
        self.tools.register(DeferTaskTool(
            ticket_manager=self.ticket_manager,
            send_callback=self.bus.publish_outbound,
            master_channels=master_channels,
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
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except BaseException:
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

    def _set_tool_context_on_registry(self, registry: ToolRegistry, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info in a specific registry."""
        for name in ("message", "spawn", "cron"):
            if tool := registry.get(name):
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
        decoder = json.JSONDecoder()
        # Capture everything between <tool_call> and </tool_call>
        matches = re.finditer(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", text)
        for i, m in enumerate(matches):
            try:
                raw = m.group(1).strip()
                # Find the first opening brace
                start = raw.find("{")
                if start == -1:
                    continue
                
                # Use raw_decode to intelligently find the end of the JSON object
                # and ignore trailing whitespace or tags.
                json_str = raw[start:]
                data, _ = decoder.raw_decode(json_str)
                
                if "name" in data:
                    calls.append(SimpleNamespace(
                        id=f"ext-{i}",
                        name=data["name"],
                        arguments=data.get("arguments", {}),
                        function=SimpleNamespace(
                            name=data["name"],
                            arguments=json.dumps(data.get("arguments", {}))
                        )
                    ))
            except Exception as e:
                logger.warning("Failed to parse inline <tool_call> block {}: {}", i, e)
                continue
        return calls

    def _find_message_in_jsonl(self, path: Path, msg_id: str, limit: int = 100) -> dict[str, Any] | None:
        """Search for a message by dingtalk_msg_id in a JSONL file, scanning backwards."""
        if not path.exists():
            return None
        
        try:
            # We use a simple but effective backward line-by-line search for memory efficiency
            with open(path, "rb") as f:
                f.seek(0, 2)  # Go to end
                pos = f.tell()
                buffer = bytearray()
                lines_found = 0
                
                while pos > 0 and lines_found < limit:
                    pos -= 1
                    f.seek(pos)
                    char = f.read(1)
                    if char == b"\n":
                        if buffer:
                            try:
                                line = buffer[::-1].decode("utf-8")
                                data = json.loads(line)
                                if data.get("metadata", {}).get("dingtalk_msg_id") == msg_id:
                                    return data
                            except Exception:
                                pass
                            lines_found += 1
                            buffer = bytearray()
                    else:
                        buffer.extend(char)
                
                # Final check for first line
                if buffer:
                    try:
                        line = buffer[::-1].decode("utf-8")
                        data = json.loads(line)
                        if data.get("metadata", {}).get("dingtalk_msg_id") == msg_id:
                            return data
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Error searching message in {}: {}", path.name, e)
        
        return None

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
        tools: ToolRegistry | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop. Returns (final_content, tools_used, messages)."""
        messages = initial_messages
        iteration = 0
        sop_retried = False
        final_content = None
        tools_used: list[str] = []

        # Use provided tools or fall back to self.tools
        active_tools = tools or self.tools

        tool_defs = active_tools.get_definitions() if self.tool_use else None
        tools_disabled = not self.tool_use
        if tools_disabled:
            logger.info("Tool use disabled by config for model {}", self.model)

        while iteration < self.max_iterations:
            iteration += 1

            t0 = time.monotonic()
            logger.info("LLM call #{} starting...{}", iteration, " (no tools)" if tools_disabled else "")
            
            if messages:
                logger.debug("▶️ [LLM Input] To Model {}:\n{}", self.model, json.dumps(messages[-1:], ensure_ascii=False, indent=2))
                
                # Full context debugging (Phase 34)
                if hasattr(self, "debug_context") and self.debug_context:
                    try:
                        debug_dir = self.workspace / "sessions" / "debug"
                        debug_dir.mkdir(parents=True, exist_ok=True)
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        # We try to get session key from current tools context or use general tag
                        debug_file = debug_dir / f"debug_{ts}.json"
                        with open(debug_file, "w", encoding="utf-8") as f:
                            json.dump({
                                "model": self.model,
                                "iteration": iteration,
                                "timestamp": datetime.now().isoformat(),
                                "messages": messages
                            }, f, ensure_ascii=False, indent=2)
                        logger.info("Full conversation context exported to {}", debug_file)
                    except Exception as e:
                        logger.warning("Failed to export debug context: {}", e)
                
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
                preview = response.content[:200] + "..." if len(response.content) > 200 else response.content
                logger.info("◀️ [LLM Output] Content (preview):\n{}", preview)
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
                    
                    # ONLY strip tags if we actually extracted something.
                    # This prevents content "disappearing" on parse failure.
                    response.content = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", response.content).strip()
                    if not response.content or not response.content.strip():
                        response.content = None
                else:
                    # If extraction failed but tags are present, keeping the content 
                    # allows the SOP retry logic or the user to see what went wrong.
                    logger.info("Retaining <tool_call> tags in content due to extraction failure")

            # Initialize 'clean' content (stripped of <think> blocks) for downstream logic
            clean = self._strip_think(response.content) if response.content else None

            if response.has_tool_calls:
                if on_progress and clean:
                    await on_progress(clean)
                if on_progress:
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
                    result = await active_tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                # SOP Override: If content is too short/denial and no tools were used, 
                # force the model to explain properly as per AGENTS.md Section 5.
                denial_keywords = ["查不了", "无法查询", "没有工具", "无权", "不编造"]
                if (
                    clean and len(clean) < 20 
                    and any(kw in clean for kw in denial_keywords)
                    and not tools_used
                    and iteration < self.max_iterations
                    and not sop_retried
                ):
                    logger.warning("Detected terse denial '{}'. Forcing SOP-compliant explanation.", clean)
                    sop_retried = True
                    messages.append({
                        "role": "user", 
                        "content": (
                            "注意：根据《AGENTS SOP》第 5 条‘坦诚无能’原则，"
                            "如果因为工具缺失或配置问题无法完成任务，请诚实、平实地用人类大白话向用户详细汇报物理工具的缺失原因，"
                            "禁止使用极简短句或傲慢的比喻。请重新生成您的汇报内容。"
                        )
                    })
                    continue

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
        """Process a message under the session lock."""
        lock = self._session_locks.setdefault(msg.session_key, asyncio.Lock())
        async with lock:
            try:
                # --- [SESSION QUOTE RECOVERY (Scheme N: Scenario-aware Thread)] ---
                quote_id = msg.metadata.get("quote_msg_id")
                # conversation_type is available in msg.metadata (from dingtalk.py) but will be stripped later
                is_group_scene = msg.metadata.get("conversation_type") == "2"
                
                if quote_id and "[引用自" not in msg.content:
                    logger.info("Recovering thread chain for quote_id={} (Group={})", quote_id, is_group_scene)
                    session = self.sessions.get_or_create(msg.session_key)
                    
                    # 1. Recursive Search Strategy (Multi-source: Memory -> Session Persistence -> Heartbeat)
                    task_ids = {quote_id}
                    heartbeat_path = self.workspace / "sessions" / "heartbeat.jsonl"
                    
                    # 1a. Trace Upward (Ancestors)
                    curr_search = quote_id
                    while curr_search:
                        found_node = None
                        
                        # Phase 1: Search Memory / Current Session (L1/L2)
                        for m in reversed(session.messages):
                            if m.get("metadata", {}).get("dingtalk_msg_id") == curr_search:
                                found_node = m
                                break
                        
                        # Phase 2: Search Heartbeat Log (L3)
                        if not found_node:
                            found_node = self._find_message_in_jsonl(heartbeat_path, curr_search, limit=self.memory_window)
                            if found_node:
                                logger.debug("L3 Hit: Found message {} in heartbeat.jsonl", curr_search)
                        
                        if found_node:
                            parent_id = found_node.get("metadata", {}).get("quote_msg_id")
                            if parent_id and parent_id not in task_ids:
                                task_ids.add(parent_id)
                                curr_search = parent_id
                            else:
                                curr_search = None
                        else:
                            curr_search = None
                    
                    # 1b. Trace Downward/Sideways - Group ONLY
                    if is_group_scene:
                        prev_size = 0
                        while len(task_ids) > prev_size:
                            prev_size = len(task_ids)
                            for m in session.messages:
                                m_meta = m.get("metadata", {})
                                mid = m_meta.get("dingtalk_msg_id")
                                qid = m_meta.get("quote_msg_id")
                                if qid in task_ids and mid and mid not in task_ids:
                                    task_ids.add(mid)

                    # 1c. Collect session messages
                    related_msgs = []
                    # First, grab from memory
                    for m in session.messages:
                        mid = m.get("metadata", {}).get("dingtalk_msg_id")
                        if mid in task_ids:
                            related_msgs.append(m)
                    
                    # Second, grab missing blocks from Heartbeat (L3)
                    found_ids = {m.get("metadata", {}).get("dingtalk_msg_id") for m in related_msgs}
                    missing_ids = task_ids - found_ids
                    if missing_ids:
                        for mid in missing_ids:
                            h_msg = self._find_message_in_jsonl(heartbeat_path, mid, limit=self.memory_window)
                            if h_msg:
                                related_msgs.append(h_msg)
                    
                    if related_msgs:
                        # 3. Sort by timestamp
                        related_msgs.sort(key=lambda x: x.get("timestamp", ""))
                        
                        # 4. Format prompt header
                        timeline_str = ""
                        for rm in related_msgs:
                            role = rm.get("role", "unknown")
                            r_meta = rm.get("metadata", {})
                            name = r_meta.get("sender_name") or (f"{self.context.agent_name}(我)" if role == "assistant" else "用户")
                            timestamp = rm.get("timestamp", "")[11:16] # HH:MM
                            r_content = self._strip_think(rm.get("content", ""))
                            timeline_str += f"[{timestamp}] {name}: {r_content}\n"
                        
                        msg.metadata["quote_context_header"] = (
                            f"【重要上下文：讨论话题链回溯】\n"
                            f"注意：以下是你当前回复的直接背景。请务必结合该话题链条中的信息进行精准且连贯的回复。\n"
                            f"------------------\n"
                            f"{timeline_str}"
                            f"------------------\n"
                        )
                        logger.success("Thread recovered ({}): {} segments", "Tree" if is_group_scene else "Linear", len(related_msgs))
                
                # --- [IMMEDIATE PERSISTENCE] ---
                # Save the user message immediately for durability. 
                # ContextBuilder will handle the extraction/deduplication to ensure LLM payload remains clean.
                session = self.sessions.get_or_create(msg.session_key)
                is_group_persistence = msg.metadata.get("conversation_type") == "2"
                persist_meta = self._clean_metadata(msg.metadata, is_group_persistence)
                
                # Global idempotency check for incoming messages
                msg_id = msg.metadata.get("dingtalk_msg_id")
                if not any(m.get("metadata", {}).get("dingtalk_msg_id") == msg_id for m in session.messages):
                    self._save_turn(session, [{"role": "user", "content": msg.content, "metadata": persist_meta}], 0)
                    self._prune_session_if_needed(session)
                    self.sessions.save(session)
                    logger.debug("User message persisted (Safe-Flash)")
                else:
                    logger.info("Message {} already exists in session, skipping save", msg_id)

                # Scheme D: Atomic processing
                await self._process_message(msg)
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
        is_system_internal: bool = False,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # --- [PRE-PROCESSING (e.g. Deterministic Profile Sync)] ---
        if self._pre_process_hook:
            try:
                await self._pre_process_hook(msg)
            except Exception as e:
                logger.error("Pre-process hook failed: {}", e)

        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            
            # --- [TOOL CONTEXT ISOLATION] ---
            from nanobot.agent.tools.registry import ToolRegistry
            local_tools = ToolRegistry()
            # Tools that need context isolation
            stateful_tools = {"message", "spawn", "cron", "escalate_to_master", "defer_to_background", "send_cross_chat", "search_chat_history", "read_full_profile"}
            for name in self.tools.tool_names:
                tool = self.tools.get(name)
                if name in stateful_tools:
                    tool = copy.copy(tool)
                local_tools.register(tool)

            self._set_tool_context_on_registry(local_tools, channel, chat_id, msg.metadata.get("message_id"))
            
            history = session.get_history(max_messages=self.memory_window)
            
            is_master_identity = False
            if self.channels_config and getattr(self.channels_config, channel, None):
                channel_cfg = getattr(self.channels_config, channel)
                # For system messages, it is usually initiated by cli or single event, so treat as private
                if hasattr(channel_cfg, "master_ids") and msg.sender_id in channel_cfg.master_ids:
                    is_master_identity = True

            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
                is_master=is_master_identity,
                current_user_id=msg.sender_id
            )
            final_content, _, all_msgs = await self._run_agent_loop(messages, tools=local_tools)
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.debug("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        is_master_identity = False
        conv_type = msg.metadata.get("conversation_type")
        if self.channels_config:
            # Safely check across all configured channels
            for field_name in self.channels_config.model_fields.keys():
                channel_cfg = getattr(self.channels_config, field_name, None)
                if channel_cfg and hasattr(channel_cfg, "master_ids"):
                    if msg.sender_id in channel_cfg.master_ids:
                        is_master_identity = True
                        break
                
        # Context privilege: Master only gets global RW and unrestricted context in private chats 
        is_master_context = is_master_identity and conv_type != "2"

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)
        
        # --- Log Raw User Message to Shadow Log ---
        # Handle dataclass serialization and datetime JSON compatibility
        from dataclasses import asdict
        msg_dict = asdict(msg)
        msg_dict["timestamp"] = msg.timestamp.isoformat() if hasattr(msg.timestamp, "isoformat") else str(msg.timestamp)
        self._log_raw_history(key, msg_dict)

        # Dynamically record group name for cross-chat search
        conv_type = msg.metadata.get("conversation_type")
        conv_title = msg.metadata.get("conversation_title")
        if conv_type == "2" and conv_title:
            await self.memory_store.save_group_info(msg.chat_id, conv_title)

        # Scheme D: Atomic processing

        cmd = msg.content.strip().lower()
        if cmd == "/new":
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())
            self._consolidating.add(session.key)
            try:
                async with lock:
                    # FIX: Safely slice using modern anchor ID instead of obsolete numeric index.
                    start_idx = 0
                    if session.last_consolidated_id:
                        for i, m in enumerate(session.messages):
                            if m.get("metadata", {}).get("dingtalk_msg_id") == session.last_consolidated_id:
                                start_idx = i + 1
                                break
                    snapshot = session.messages[start_idx:]
                    if snapshot:
                        temp = Session(key=session.key)
                        temp.messages = list(snapshot)
                        if not await self._consolidate_memory(temp, current_user_id=msg.sender_id, is_master=is_master_context, archive_all=True):
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
                                  content=f"🐈 {self.context.agent_name} commands:\n/new — Start a new conversation\n/stop — Stop the current task\n/help — Show available commands")

        # Scheme N & O: Robust ID-based accumulation check
        # Index(last_consolidated_id) splits history from "now"
        anchor_idx = -1
        if session.last_consolidated_id:
            for i, m in enumerate(session.messages):
                if m.get("metadata", {}).get("dingtalk_msg_id") == session.last_consolidated_id:
                    anchor_idx = i
                    break

        # Gross accumulation since last consolidation
        accumulated = len(session.messages) - (anchor_idx + 1)
        
        # Net accumulation (excluding logic-protected Safe Buffer)
        # This prevents triggering when there's nothing harvestable after buffer reservation
        safe_buffer = getattr(self, "session_safe_buffer", 0)
        session.session_safe_buffer = safe_buffer  # Scheme N: Sync the attribute for MemoryStore
        net_unconsolidated = accumulated - safe_buffer
        
        # [DEBUG LOG] Pure ID-based check
        logger.info("Consolidation check for {}: anchor_id={}, anchor_idx={}, net_sum={}, buffer={}, window={}", 
                    session.key, session.last_consolidated_id, anchor_idx, net_unconsolidated, safe_buffer, self.memory_window)

        # Identify relationship for specialized memory rules
        is_master_context = False
        if self.channels_config and msg.channel in self.channels_config:
            chan_cfg = self.channels_config[msg.channel]
            if hasattr(chan_cfg, "master_ids") and msg.sender_id in chan_cfg.master_ids:
                is_master_context = True

        if (net_unconsolidated >= self.memory_window and session.key not in self._consolidating):
            self._consolidating.add(session.key)
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())

            async def _consolidate_and_unlock():
                try:
                    async with lock:
                        await self._consolidate_memory(session, current_user_id=msg.sender_id, is_master=is_master_context, is_master_identity=is_master_identity)
                finally:
                    self._consolidating.discard(session.key)
                    _task = asyncio.current_task()
                    if _task is not None:
                        self._consolidation_tasks.discard(_task)

            _task = asyncio.create_task(_consolidate_and_unlock())
            self._consolidation_tasks.add(_task)

        # --- [TOOL CONTEXT ISOLATION] ---
        from nanobot.agent.tools.registry import ToolRegistry
        local_tools = ToolRegistry()
        # Tools that need context isolation
        stateful_tools = {"message", "spawn", "cron", "escalate_to_master", "defer_to_background", "send_cross_chat", "search_chat_history", "read_full_profile", "memorize_fact"}
        for name in self.tools.tool_names:
            tool = self.tools.get(name)
            if name in stateful_tools:
                tool = copy.copy(tool)
            local_tools.register(tool)

        self._set_tool_context_on_registry(local_tools, msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        
        if mem_tool := local_tools.get("memorize_fact"):
            if isinstance(mem_tool, MemorizeFactTool):
                mem_tool.set_context(is_master=is_master_identity)

        if message_tool := local_tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()
        
        if escalate_tool := local_tools.get("escalate_to_master"):
            if isinstance(escalate_tool, EscalateToMasterTool):
                sender_name = msg.metadata.get("sender_name", "")
                escalate_tool.start_turn(msg.channel, msg.chat_id, msg.sender_id, guest_name=sender_name)

        if defer_tool := local_tools.get("defer_to_background"):
            from nanobot.agent.tools.defer import DeferTaskTool
            if isinstance(defer_tool, DeferTaskTool):
                sender_name = msg.metadata.get("sender_name", "")
                defer_tool.start_turn(msg.channel, msg.chat_id, msg.sender_id, guest_name=sender_name)

        if cross_chat_tool := local_tools.get("send_cross_chat"):
            if isinstance(cross_chat_tool, SendCrossChatTool):
                # Identity grants cross-chat permissions regardless of group context
                cross_chat_tool.set_context(sender_id=msg.sender_id, is_master=is_master_identity)

        if search_tool := local_tools.get("search_chat_history"):
            from workspace.skills.staff_memory_expert.logic import SearchChatHistoryTool
            if isinstance(search_tool, SearchChatHistoryTool):
                search_tool.set_context(user_id=msg.sender_id, is_master=is_master_identity)

        if profile_tool := local_tools.get("read_full_profile"):
            from workspace.skills.staff_memory_expert.logic import ReadFullProfileTool
            if isinstance(profile_tool, ReadFullProfileTool):
                profile_tool.set_context(user_id=msg.sender_id, is_master=is_master_identity)

        history = session.get_history(max_messages=self.memory_window)
        
        # Scheme P: Skip input sanitizer for authorized internal system calls or Master identities
        skip_sanitizer = False
        if is_system_internal:
            logger.info("Skipping Sanitizer: Message marked as system-internal for {}", msg.sender_id)
            skip_sanitizer = True

        if not is_master_identity and not skip_sanitizer:
            from nanobot.agent.sanitizer import SanitizerAgent
            sanitizer = SanitizerAgent(self.provider, self.model)
            t_san = time.monotonic()
            verdict, sanitizer_msg = await sanitizer.sanitize_input(msg.content, is_master=is_master_identity)
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
                            summary=f"[安全拦截] 访客 {guest_name} 的消息触发了安全审查: {sanitizer_msg}",
                            pacifier_message=""
                        )
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="这个问题我需要跟老板确认一下才能答复您，请您稍等，我马上帮您跟进。",
                    metadata=msg.metadata or {},
                )

        # Scheme M: Dynamic Context Injection & Transparency
        effective_content = msg.content
        if header := msg.metadata.get("quote_context_header"):
            effective_content = f"{header}{msg.content}"
            logger.info("DEBUG: Full Prompt for LLM:\n{}", effective_content)

        # Ultra-light routing: determine if we can skip loading the huge 5000-word Markdown profile
        use_cold_boot = self._should_use_cold_boot(session, effective_content)
        if use_cold_boot:
            logger.info("Cold-Boot Routing Engaged: Mounting lightweight profile snapshot for '{}'", msg.sender_id)

        initial_messages = self.context.build_messages(
            history=history,
            current_message=effective_content,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
            is_master=is_master_context,
            current_user_id=msg.sender_id,
            sender_name=msg.metadata.get("sender_name", ""),
            use_summary=use_cold_boot,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        final_content, tools_used, all_msgs = await self._run_agent_loop(
            initial_messages, on_progress=on_progress or _bus_progress,
            tools=local_tools
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        if True: # Always audit, but pass identity to the auditor to bypass blocks
            from nanobot.agent.sanitizer import SanitizerAgent
            sanitizer = SanitizerAgent(self.provider, self.model)
            t_aud = time.monotonic()
            audited_content = await sanitizer.audit_output(final_content, is_master=is_master_identity)
            logger.info("Sanitizer output audit took {:.1f}s", time.monotonic() - t_aud)
            
            if audited_content != final_content:
                final_content = audited_content
                # Rewrite the last assistant message in internal history so it doesn't remember the leaked version
                if all_msgs and all_msgs[-1]["role"] == "assistant":
                    all_msgs[-1]["content"] = final_content
            
            # Store original final_content for persistence, use outbound_content for the external world
            # This must be initialized here to avoid UnboundLocalError in regular flows
            outbound_content = final_content
            if final_content != audited_content:
                outbound_content = audited_content

        import uuid
        correlation_id = str(uuid.uuid4())
        
        # Scheme D: Atomic Sync Send
        # If we have content to send, publish it now and WAIT for the receipt before saving
        remote_msg_id = None
        is_msg_tool = (mt := local_tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn
        
        if not is_msg_tool:
            outbound = OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=outbound_content,
                metadata=msg.metadata or {},
                correlation_id=correlation_id
            )
            # 1. Publish to bus
            await self.bus.publish_outbound(outbound)
            
            # 2. Synchronously wait for remote message ID (timeout protection)
            logger.info("Waiting for receipt ID for correlation_id={}...", correlation_id)
            remote_msg_id = await self.bus.wait_for_receipt(correlation_id, timeout=3.0)
            if remote_msg_id:
                logger.info("Successfully received remote ID {} for {}", remote_msg_id, correlation_id)
            else:
                logger.warning("Timed out waiting for receipt for {}. Saving without remote ID.", correlation_id)
        else:
            # Scheme N: Handle Tool-based message receipt
            if hasattr(mt, "_last_correlation_id") and mt._last_correlation_id:
                tool_corr_id = mt._last_correlation_id
                logger.info("Waiting for Tool-receipt ID for correlation_id={}...", tool_corr_id)
                remote_msg_id = await self.bus.wait_for_receipt(tool_corr_id, timeout=3.0)
                if remote_msg_id:
                    logger.info("Successfully received Tool-remote ID {} for {}", remote_msg_id, tool_corr_id)

        # 3. Inject IDs into metadata before saving to session
        if all_msgs and all_msgs[-1]["role"] == "assistant":
             all_msgs[-1].setdefault("metadata", {})["correlation_id"] = (mt._last_correlation_id if is_msg_tool else correlation_id)
             if remote_msg_id:
                 all_msgs[-1]["metadata"]["dingtalk_msg_id"] = remote_msg_id
             # Apply the audited/fallback content to the persistent history
             all_msgs[-1]["content"] = final_content

        # 4. Save only new turns (Scheme N: ROLE ISOLATION)
        # Identify group scene (this info is transient in all_msgs metadata)
        is_group_save = msg.metadata.get("conversation_type") == "2"
        skip = 1 + len(history)
        for m in all_msgs[skip:]:
            if m.get("role") == "user":
                continue 
            
            if m.get("metadata"):
                m["metadata"] = self._clean_metadata(m["metadata"], is_group_save)
            # Save Assistant/Tool/System turns
            self._save_turn(session, [m], 0)
        
        # Scheme O: Automatic Session Pruning (Rolling Cleanup)
        self._prune_session_if_needed(session)
        self.sessions.save(session)

        # Ensure guest memory file exists for non-master users on first contact.
        if not is_master_identity and msg.sender_id not in ("Unknown", "user"):
            guest_file = self.memory_store._get_guest_file(msg.sender_id)
            if not guest_file.exists():
                from datetime import datetime as _dt
                sender_name = msg.metadata.get("sender_name", "")
                initial = (
                    f"---\nTrustScore: 50\n---\n"
                    f"## Guest: {sender_name} ({msg.sender_id})\n\n"
                    f"- 首次互动: {_dt.now().strftime('%Y-%m-%d %H:%M')}\n"
                    f"- 来源: {msg.channel}\n"
                )
                self.memory_store.write_guest(msg.sender_id, initial)
                logger.info("Created initial guest memory for {} ({})", sender_name, msg.sender_id)

        if not is_msg_tool:
             logger.info("🤖 Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        
        return None  # Message already published in Scheme D

    def _clean_metadata(self, metadata: dict, is_group: bool) -> dict:
        """Sanitize metadata for Session storage based on Scheme O."""
        clean = dict(metadata)
        # Always remove massive prompt headers and temporary flags
        clean.pop("quote_context_header", None)
        clean.pop("quote_text", None)
        clean.pop("conversation_type", None)
        clean.pop("platform", None)
        clean.pop("conversation_title", None)
        clean.pop("correlation_id", None)  # Scheme O: Remove debugging correlation IDs
        
        if not is_group:
            # Private chat: kill identity markers to keep it 100% clean
            clean.pop("sender_name", None)
            clean.pop("sender_id", None)
        
        return clean

    def _prune_session_if_needed(self, session: Session) -> bool:
        """Keep session size under control based on user configuration (Scheme O)."""
        is_background = session.key == "heartbeat" or session.key.startswith("cron:")
        
        if is_background:
            limit = self.session_background_max_messages
            target = self.session_background_clear_to_size
        else:
            limit = self.session_max_messages
            target = self.session_clear_to_size
        
        if len(session.messages) > limit:
            to_remove = len(session.messages) - target
            logger.info("Pruning session {}: size {} exceeds limit {}. Removing oldest {} messages.", 
                        session.key, len(session.messages), limit, to_remove)
            # Remove oldest messages
            session.messages = session.messages[to_remove:]
            # Core Fix: No longer need to manually shift last_consolidated.
            # Shift existing pointers and record the new ID anchor (Scheme N: Robust Slicing)
            # MemoryStore.consolidate has already updated the session object in memory.
            return True
        return False

    def _log_raw_history(self, session_key: str, message: dict) -> None:
        """Log conversation history in an append-only JSONL file (The Shadow Log).
        
        This version is optimized for human reading:
        - Skips 'tool' role messages.
        - Strips 'tool_calls' from 'assistant' messages.
        """
        role = message.get("role")
        
        # 1. 彻底不记录 tool 角色的回复 (人类不需要看)
        if role == "tool":
            return
            
        clean_msg = dict(message)
        
        # 2. 剔除助手消息中的 tool_calls 技术细节 (保持日志纯净)
        if role == "assistant" and "tool_calls" in clean_msg:
            # 如果助手既有文字又有 tool_calls，只保留文字
            # 如果助手只有 tool_calls (中间步骤)，则不记录到日志，避免出现 content: null
            if not clean_msg.get("content"):
                return
            clean_msg.pop("tool_calls", None)

        import json
        from nanobot.utils.helpers import safe_filename
        safe_key = safe_filename(session_key.replace(":", "_"))
        path = self.raw_history_dir / f"{safe_key}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(clean_msg, ensure_ascii=False) + "\n")

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session and shadow log with divergent logic."""
        from datetime import datetime
        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            
            # --- 数据脱敏/压缩 ---
            if role == "assistant":
                if not content and not entry.get("tool_calls"):
                    continue
                # 剔除冗长的思维链，节省内存
                entry.pop("reasoning_content", None)
                entry.pop("thinking_blocks", None)
            
            if role == "tool" and isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
                entry["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                    continue
            
            entry.setdefault("timestamp", datetime.now().isoformat())
            
            # --- 分支 1: 写入影子日志 (面向主人：极致纯净，剔除所有技术噪音) ---
            self._log_raw_history(session.key, entry)
            
            # --- 分支 2: 保存到实时会话 (面向机器：保留逻辑链，支持 tool 记录) ---
            # 注意：此处不再 continue，确保 role: tool 也能进入 session.messages
            session.messages.append(entry)
            
        session.updated_at = datetime.now()

    async def _consolidate_memory(self, session, current_user_id: str = "Unknown", is_master: bool = False, is_master_identity: bool = False, archive_all: bool = False) -> bool:
        """Delegate consolidation to staff-memory-expert skill."""
        consolidate_tool = self.tools.get("consolidate_memory")
        if not consolidate_tool:
            logger.error("ConsolidateMemoryTool not found in registry")
            return False
            
        success = await consolidate_tool.run_consolidation(
            session, self.provider, self.model,
            memory_window=self.memory_window,
            current_user_id=current_user_id,
            is_master=is_master
        )
        
        if success:
            # Scheme N: Crucial - Persistence is required after header/anchor update
            self.sessions.save(session)
            logger.info("Memory consolidation: Session state persisted for {}", session.key)

        if success and not is_master_identity and current_user_id != "Unknown" and current_user_id != "user":
            async def _background_tasks():
                try:
                    mem_store = MemoryStore(self.workspace)
                    
                    # 1. Background Reflection (Existing)
                    from nanobot.agent.reflection import ReflectionAgent
                    agent = ReflectionAgent(mem_store, self.provider, self.model)
                    alert = await agent.reflect_on_guest(current_user_id)
                    
                    if alert:
                        if self.channels_config and getattr(self.channels_config, 'dingtalk', None):
                            dt_cfg = getattr(self.channels_config, 'dingtalk')
                            if hasattr(dt_cfg, 'master_ids') and getattr(dt_cfg, 'master_ids', None):
                                from nanobot.bus.events import OutboundMessage
                                for m_id in dt_cfg.master_ids:
                                    logger.info("Forwarding reflection alert to master {}", m_id)
                                    await self.bus.publish_outbound(OutboundMessage(
                                        channel="dingtalk", chat_id=m_id,
                                        content=f"⚠️ {alert}"
                                    ))

                    # 2. Dream Purification: Generate/Update Profile Snapshot (Snapshot Update)
                    # This ensures the 'Cold-Boot' summary is always fresh.
                    await mem_store.purify_guest_memory(current_user_id, self.provider, self.model)

                    # 3. Memory Pruning: Deep refine the physical file (Selective Cleanup)
                    # Trigger only if file is bulky (> 2KB) or after a certain conversation depth.
                    guest_file = mem_store._get_guest_file(current_user_id)
                    if guest_file.exists() and guest_file.stat().st_size > 2048:
                        logger.info("Triggering deep memory pruning for heavy guest archive: {}", current_user_id)
                        await mem_store.prune_guest_memory(current_user_id, self.provider, self.model)

                except Exception:
                    logger.exception("Background memory tasks (Reflect/Purify/Prune) failed")

            _task = asyncio.create_task(_background_tasks())
            if hasattr(self, '_consolidation_tasks'):
                self._consolidation_tasks.add(_task)

        return success

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        sender_id: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        is_system_internal: bool = False,
    ) -> str:
        """Process a message directly (for CLI, cron, or heartbeat usage).
        
        If sender_id is not provided, attempts to use the first configured master_id
        so that system-triggered messages (cron/heartbeat) are treated as Master
        and skip the Sanitizer.
        """
        await self._connect_mcp()
        if not sender_id:
            # Try to resolve a master ID so system calls aren't treated as Guest
            if self.channels_config and hasattr(self.channels_config, "dingtalk"):
                dt_cfg = getattr(self.channels_config, "dingtalk", None)
                if dt_cfg and hasattr(dt_cfg, "master_ids") and dt_cfg.master_ids:
                    sender_id = dt_cfg.master_ids[0]
            if not sender_id:
                sender_id = "system"
        
        # Periodic cleanup of old background sessions (triggered by any direct/background call)
        try:
            cleaned = self.sessions.cleanup_background_sessions(self.session_background_cleanup_days)
            if cleaned > 0:
                logger.info("Auto-cleanup: removed {} expired background session files", cleaned)
        except Exception:
            logger.exception("Background session cleanup failed")

        msg = InboundMessage(channel=channel, sender_id=sender_id, chat_id=chat_id, content=content)
        response = await self._process_message(
            msg, 
            session_key=session_key, 
            on_progress=on_progress, 
            is_system_internal=is_system_internal
        )
        return response.content if response else ""

    def _should_use_cold_boot(self, session: Session, current_message: str) -> bool:
        """Ultra-lightweight intention routing to save LLM context window and TTFT.
        Returns True if the message is short casual chat and history is sparse.
        """
        # If the user sends a long message, it likely requires full context/rules.
        if len(current_message) > 40:
            return False
            
        # Fast generic keywords bypass (meaning they likely need complex contexts)
        magic_words = ["老板", "金总", "谁", "认识", "我是", "我叫", "名字", "职位", "重新", "什么", "怎么", "请教", "帮忙", "文档", "系统", "搜索", "你"]
        for word in magic_words:
            if word in current_message:
                return False
                
        # If in a deep conversation block, context matters.
        if len(session.messages) > 4:
            return False
            
        # Short, possibly casual initiation like "hi", "hello", "在吗" -> use COLD BOOT (Summary only)
        return True
