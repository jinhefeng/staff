
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from nanobot.agent.memory import MemoryStore

# 模拟环境路径
TEST_WORKSPACE = Path("/tmp/staff_test_workspace")

@pytest.fixture
def memory_store():
    if TEST_WORKSPACE.exists():
        import shutil
        shutil.rmtree(TEST_WORKSPACE)
    TEST_WORKSPACE.mkdir(parents=True)
    return MemoryStore(TEST_WORKSPACE)

@pytest.mark.asyncio
async def test_prune_memory_deduplication(memory_store):
    """验证深度修剪逻辑是否能成功合并重复的雷区标签。"""
    user_id = "test_user_prune"
    
    # 1. 构造一个包含重复内容的臃肿档案
    bulky_content = """---
TrustScore: 50
---
### 🎭 人物侧写 (Persona)
- 用户是一个资深软件架构师。

### 🛡️ 核心偏好与反思 (Preferences)
- [CAUTION]: 不要提到任何有关薪资的话题。
- [CAUTION]: 严禁讨论薪水和奖金相关内容。
- [STRATEGY]: 说话要简练。
- [STRATEGY]: 保持回答简洁明了。

### 📜 客体特供口径 (Tailored Narrative)
- (空)

### 📈 现状与近期关注 (Recent/Status)
- 正在讨论项目 A 的架构设计。
"""
    memory_store.write_guest(user_id, bulky_content)
    
    # 2. 模拟 LLM Provider
    mock_provider = MagicMock()
    mock_resp = MagicMock()
    mock_resp.has_tool_calls = True
    
    # 模拟 LLM 返回的提纯后内容：合并了雷区和策略
    refined_content = """---
TrustScore: 50
---
### 🎭 人物侧写 (Persona)
- 资深软件架构师。

### 🛡️ 核心偏好与反思 (Preferences)
- [CAUTION]: 严禁讨论薪资及奖金相关话题。
- [STRATEGY]: 始终保持沟通简洁、结论先行。

### 📜 客体特供口径 (Tailored Narrative)
- (空)

### 📈 现状与近期关注 (Recent/Status)
- 聚焦项目 A 架构设计。
"""
    mock_tool_call = MagicMock()
    mock_tool_call.arguments = {"refined_content": refined_content}
    mock_resp.tool_calls = [mock_tool_call]
    
    mock_provider.chat = AsyncMock(return_value=mock_resp)
    
    # 3. 执行修剪
    success = await memory_store.prune_guest_memory(user_id, mock_provider, "test-model")
    
    # 4. 验证
    assert success is True
    final_content, _ = memory_store.read_guest(user_id)
    
    # 检查是否保留了 YAML
    assert "TrustScore: 50" in final_content
    # 检查是否执行了合并（这里通过断言 LLM 模拟结果已被写入）
    assert "严禁讨论薪资及奖金相关话题" in final_content
    assert final_content.count("[CAUTION]") == 1
    assert final_content.count("[STRATEGY]") == 1

@pytest.mark.asyncio
async def test_purify_memory_snapshot(memory_store):
    """验证画像快照生成逻辑。"""
    user_id = "test_user_purify"
    # 增加内容长度以超过 300 字符的跳过阈值
    content = "---\nTrustScore: 80\n---\n### 🎭 人物侧写 (Persona)\n" + "A very busy CEO who manages three international companies. " * 10
    memory_store.write_guest(user_id, content)
    
    mock_provider = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = "Summary: A versatile and high-energy CEO who prioritizes high-impact decisions."
    mock_provider.chat = AsyncMock(return_value=mock_resp)
    
    success = await memory_store.purify_guest_memory(user_id, mock_provider, "test-model")
    
    assert success is True
    summary, exists = memory_store.read_guest_summary(user_id)
    assert exists is True
    assert "CEO" in summary
    assert "TrustScore: 80" in summary

if __name__ == "__main__":
    import sys
    pytest.main([__file__])
