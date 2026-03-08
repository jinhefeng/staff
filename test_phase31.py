
import asyncio
from pathlib import Path
from nanobot.agent.memory import MemoryStore
from nanobot.agent.context import ContextBuilder
from nanobot.agent.tickets import TicketManager
import sys
import os

# 模拟环境
WORKSPACE = Path("/Users/jinhefeng/Dev/staff")

async def test_onboarding_logic():
    memory = MemoryStore(WORKSPACE)
    context = ContextBuilder(WORKSPACE)
    
    # 1. 验证新访客（无文件）
    user_id = "test_new_onboarding_001"
    g_file = memory._get_guest_file(user_id)
    if g_file.exists(): g_file.unlink()
    
    content, exists = memory.read_guest(user_id)
    print(f"New User - Exists: {exists}")
    
    prompt = context.build_system_prompt(current_user_id=user_id)
    if "## 首次接触引导" in prompt:
        print("✅ Onboarding SOP injected correctly.")
    else:
        print("❌ Onboarding SOP missing!")

    # 2. 验证确定性更新
    updates = {
        "LastSyncDate": "2026-03-08",
        "DeptPath": "Antigravity/AI-Team",
        "title": "Senior Architect"
    }
    memory.update_guest_deterministic(user_id, updates)
    
    new_content, _ = memory.read_guest(user_id)
    if "LastSyncDate: 2026-03-08" in new_content and "Antigravity/AI-Team" in new_content:
        print("✅ Deterministic update (YAML + Content) successful.")
    else:
        print(f"❌ Deterministic update failed! Content: {new_content[:200]}")

if __name__ == "__main__":
    asyncio.run(test_onboarding_logic())
