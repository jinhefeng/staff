import asyncio
import httpx
from nanobot.channels.dingtalk import config
import json

async def main():
    async with httpx.AsyncClient() as client:
        # Get token
        resp = await client.post("https://api.dingtalk.com/v1.0/oauth2/accessToken", json={"appKey": config.client_id, "appSecret": config.client_secret})
        token = resp.json()["accessToken"]
        
        # Search API
        url = "https://api.dingtalk.com/v1.0/contact/users/search"
        payload = {"queryWord": "姜业正", "offset": 0, "size": 10}
        resp = await client.post(url, json=payload, headers={"x-acs-dingtalk-access-token": token})
        print(resp.status_code)
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
