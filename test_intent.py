import asyncio
from unittest.mock import MagicMock
from nanobot.agent.sanitizer import SanitizerAgent

async def test():
    class MockProvider:
        def __init__(self):
            self.chat = AsyncMock()
        async def chat(self, *args, **kwargs):
            return MagicMock(content="PROMISE")
            
    class AsyncMock:
        async def __call__(self, *args, **kwargs):
            return MagicMock(content="PROMISE")

    mock_provider = MockProvider()
    agent = SanitizerAgent(mock_provider, 'test-model')
    
    res = await agent.check_promise_intent("好的，这个站挂了。我晚点帮你写个用 tushare 获取数据的版本。")
    print(f"\nTEST RESULT (Is Lip Service?): {res}\n")

asyncio.run(test())
