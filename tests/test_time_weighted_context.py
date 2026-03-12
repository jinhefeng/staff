"""Tests for time-weighted context construction."""

import datetime
from pathlib import Path
from nanobot.agent.context import ContextBuilder

def test_relative_time_tag_injection(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    builder = ContextBuilder(workspace)

    now = datetime.datetime.now()
    
    # 模拟不同时间点的历史消息
    history = [
        {
            "role": "user", 
            "content": "Message A", 
            "timestamp": (now - datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        },
        {
            "role": "assistant", 
            "content": "Message B", 
            "timestamp": (now - datetime.timedelta(minutes=35)).strftime("%Y-%m-%d %H:%M:%S")
        },
        {
            "role": "user", 
            "content": "Message C", 
            "timestamp": (now - datetime.timedelta(seconds=20)).strftime("%Y-%m-%d %H:%M:%S")
        }
    ]

    messages = builder.build_messages(
        history=history,
        current_message="Latest Message",
        channel="cli",
        chat_id="direct"
    )

    # 验证消息条数：1 system + 3 history + 1 runtime + 1 lastMsg = 6
    assert len(messages) == 6

    # 验证标签注入
    assert "[2小时前] Message A" in messages[1]["content"]
    assert "[1小时内] Message B" in messages[2]["content"]
    assert "[刚才] Message C" in messages[3]["content"]
    
    # 验证最新消息不带标签（由 Runtime Context 负责时间）
    assert messages[-1]["content"] == "Latest Message"

def test_time_binning_for_cache_stability(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    builder = ContextBuilder(workspace)
    
    now = datetime.datetime.now()
    
    # 验证 5 分钟档位
    ts_4min = (now - datetime.timedelta(minutes=4)).strftime("%Y-%m-%d %H:%M:%S")
    ts_2min = (now - datetime.timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    
    label_4 = builder._format_relative_time(ts_4min)
    label_2 = builder._format_relative_time(ts_2min)
    
    assert label_4 == "[5分钟内]"
    assert label_2 == "[5分钟内]"
    
    # 验证 1 小时档位
    ts_45min = (now - datetime.timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
    label_45 = builder._format_relative_time(ts_45min)
    assert label_45 == "[1小时内]"
