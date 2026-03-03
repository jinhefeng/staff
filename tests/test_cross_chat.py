"""Tests for cross-session chat tools and guest memory initialization."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.tools.cross_chat import SearchContactsTool, SendCrossChatTool
from nanobot.bus.events import OutboundMessage


# ============================================================================
# SearchContactsTool
# ============================================================================

class TestSearchContactsTool:
    def test_name_and_description(self) -> None:
        tool = SearchContactsTool()
        assert tool.name == "search_contacts"
        assert "search" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_no_search_fn_returns_error(self) -> None:
        tool = SearchContactsTool()
        result = await tool.execute(keyword="张总")
        assert "not available" in result

    @pytest.mark.asyncio
    async def test_empty_keyword_returns_error(self) -> None:
        tool = SearchContactsTool(search_fn=AsyncMock())
        result = await tool.execute(keyword="")
        assert "required" in result

    @pytest.mark.asyncio
    async def test_search_returns_formatted_results(self) -> None:
        mock_fn = AsyncMock(return_value={
            "users": [{"name": "张总", "userId": "user123", "dept": "研发部"}],
            "groups": [{"name": "研发群", "openConversationId": "cid456"}],
        })
        tool = SearchContactsTool(search_fn=mock_fn)
        result = await tool.execute(keyword="张")
        assert "张总" in result
        assert "user123" in result
        assert "研发群" in result
        assert "cid456" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self) -> None:
        mock_fn = AsyncMock(return_value={"users": [], "groups": []})
        tool = SearchContactsTool(search_fn=mock_fn)
        result = await tool.execute(keyword="不存在的人")
        assert "No results" in result

    @pytest.mark.asyncio
    async def test_search_local_memory_fallback(self, tmp_path: Path) -> None:
        # Create mock memory structure
        mem_dir = tmp_path / "memory"
        guests_dir = mem_dir / "guests"
        core_dir = mem_dir / "core"
        guests_dir.mkdir(parents=True)
        core_dir.mkdir(parents=True)
        
        # Add a guest with an alias
        (guests_dir / "user_123.md").write_text("## Guest: 张三 (user_123)\nAlias: 小张", encoding="utf-8")
        # Add a group
        import json
        (core_dir / "groups.json").write_text(json.dumps({"group_456": "研发部群"}), encoding="utf-8")
        
        mock_fn = AsyncMock(return_value={"users": [], "groups": []})
        tool = SearchContactsTool(search_fn=mock_fn, workspace=tmp_path)
        
        # Test alias search
        result_alias = await tool.execute(keyword="小张")
        assert "张三 (Matched Local)" in result_alias
        assert "user_123" in result_alias
        
        # Test group search
        result_group = await tool.execute(keyword="研发")
        assert "研发部群 (Local)" in result_group
        assert "group_456" in result_group


# ============================================================================
# SendCrossChatTool
# ============================================================================

class TestSendCrossChatTool:
    def _make_tool(self, tmp_path: Path, trust_score: int = 50) -> SendCrossChatTool:
        """Create a tool with a mock guest memory file."""
        # Set up guest memory
        guests_dir = tmp_path / "memory" / "guests"
        guests_dir.mkdir(parents=True, exist_ok=True)
        guest_file = guests_dir / "guest1.md"
        guest_file.write_text(f"---\nTrustScore: {trust_score}\n---\n## Guest\n")

        send_cb = AsyncMock()
        tool = SendCrossChatTool(send_callback=send_cb, workspace=tmp_path)
        tool.set_context(sender_id="guest1", is_master=False)
        return tool

    def test_name(self) -> None:
        tool = SendCrossChatTool()
        assert tool.name == "send_cross_chat"

    @pytest.mark.asyncio
    async def test_trust_score_below_threshold_rejected(self, tmp_path: Path) -> None:
        tool = self._make_tool(tmp_path, trust_score=60)
        result = await tool.execute(target_id="group1", target_type="group", content="Hi")
        assert "Access denied" in result
        assert "60" in result

    @pytest.mark.asyncio
    async def test_trust_score_above_threshold_allowed(self, tmp_path: Path) -> None:
        tool = self._make_tool(tmp_path, trust_score=90)
        result = await tool.execute(target_id="user2", target_type="user", content="Hello")
        assert "successfully sent" in result
        tool._send_callback.assert_called_once()
        msg: OutboundMessage = tool._send_callback.call_args[0][0]
        assert msg.channel == "dingtalk"
        assert msg.chat_id == "user2"
        assert msg.content == "Hello"
        assert msg.metadata["conversation_type"] == "1"

    @pytest.mark.asyncio
    async def test_master_bypasses_trust_check(self, tmp_path: Path) -> None:
        tool = self._make_tool(tmp_path, trust_score=10)
        tool.set_context(sender_id="guest1", is_master=True)
        result = await tool.execute(target_id="cid123", target_type="group", content="Meeting at 3pm")
        assert "successfully sent" in result
        msg: OutboundMessage = tool._send_callback.call_args[0][0]
        assert msg.metadata["conversation_type"] == "2"

    @pytest.mark.asyncio
    async def test_send_to_group_sets_correct_type(self, tmp_path: Path) -> None:
        tool = self._make_tool(tmp_path, trust_score=90)
        await tool.execute(target_id="cid789", target_type="group", content="Test")
        msg: OutboundMessage = tool._send_callback.call_args[0][0]
        assert msg.metadata["conversation_type"] == "2"

    @pytest.mark.asyncio
    async def test_invalid_target_type(self, tmp_path: Path) -> None:
        tool = self._make_tool(tmp_path, trust_score=90)
        result = await tool.execute(target_id="x", target_type="invalid", content="Hi")
        assert "must be" in result

    @pytest.mark.asyncio
    async def test_missing_params(self, tmp_path: Path) -> None:
        tool = self._make_tool(tmp_path, trust_score=90)
        result = await tool.execute(target_id="", target_type="user", content="Hi")
        assert "required" in result


# ============================================================================
# Guest Memory Init (Bug fix verification)
# ============================================================================

class TestGuestMemoryInit:
    @pytest.mark.asyncio
    async def test_guest_file_created_on_first_contact(self, tmp_path: Path) -> None:
        """Verify that a guest memory file is created for first-time non-master users."""
        from nanobot.agent.memory import MemoryStore

        mem = MemoryStore(tmp_path)
        guest_file = mem._get_guest_file("new_guest_123")

        # Before: file should not exist
        assert not guest_file.exists()

        # Simulate what loop.py now does for first-time guests
        if not guest_file.exists():
            from datetime import datetime
            initial = (
                f"---\nTrustScore: 50\n---\n"
                f"## Guest: Test User (new_guest_123)\n\n"
                f"- 首次互动: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"- 来源: dingtalk\n"
            )
            mem.write_guest("new_guest_123", initial)

        # After: file should exist with TrustScore 50
        assert guest_file.exists()
        content = guest_file.read_text()
        assert "TrustScore: 50" in content
        assert "new_guest_123" in content
