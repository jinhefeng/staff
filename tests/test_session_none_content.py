
import pytest
from nanobot.session.manager import Session

def test_get_history_with_none_content():
    """验证当消息 content 为 None 时，get_history 不会崩溃。"""
    session = Session(key="test:123")
    
    # 模拟多种边界情况
    session.add_message("user", "Hello")
    
    # 手动插入 content 为 None 的 tool 消息
    session.messages.append({
        "role": "tool",
        "content": None,
        "tool_call_id": "call_1",
        "name": "test_tool"
    })
    
    # 模拟超过限制但为 None 的内容（逻辑上不应发生，但作为稳健性测试）
    session.messages.append({
        "role": "tool",
        "content": None,
        "tool_call_id": "call_2",
        "name": "test_tool"
    })
    
    # 确保之前的信息足以触发索引判断 (msg_count > 2)
    session.add_message("assistant", "Hi there")
    
    # 调用 get_history
    try:
        history = session.get_history(max_messages=10)
        assert len(history) > 0
        # 验证 None 已被转换为 ""
        tool_msgs = [m for m in history if m["role"] == "tool"]
        for m in tool_msgs:
            assert m["content"] == ""
            assert isinstance(m["content"], str)
    except TypeError as e:
        pytest.fail(f"get_history failed with TypeError: {e}")

def test_get_history_truncation_safety():
    """验证长内容的 tool 消息依然可以正常截断且不报错。"""
    session = Session(key="test:456")
    long_content = "A" * 2000
    
    session.add_message("user", "long job")
    session.messages.append({
        "role": "tool",
        "content": long_content,
        "tool_call_id": "call_long"
    })
    session.add_message("assistant", "Done")
    # 为了让 tool 消息处于 i < msg_count - 2 的位置，再加一条
    session.add_message("user", "next")
    
    history = session.get_history()
    tool_msg = next(m for m in history if m["role"] == "tool")
    
    assert len(tool_msg["content"]) < 2000
    assert "[... Content truncated" in tool_msg["content"]
