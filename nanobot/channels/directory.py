"""DingTalk organization directory API wrapper.

Provides methods to search users and groups in the organization
via DingTalk OpenAPI v1.0, for cross-session messaging capabilities.
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger


class DingTalkDirectory:
    """DingTalk organization directory search via OpenAPI v1.0."""

    # All v1.0 APIs use header-based auth instead of query-param token
    _BASE = "https://api.dingtalk.com"

    def __init__(self, http: httpx.AsyncClient, get_token_fn):
        """
        Args:
            http: Shared async HTTP client.
            get_token_fn: Async callable returning the access token string.
        """
        self._http = http
        self._get_token = get_token_fn

    def _headers(self, token: str) -> dict[str, str]:
        return {"x-acs-dingtalk-access-token": token}

    async def search_users(self, keyword: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search organization users by keyword (name / pinyin).

        Returns list of dicts: [{name, userId, dept}, ...]
        Uses: POST /v1.0/contact/users/search
        Requires permission: 通讯录用户搜索 (qyapi_get_member)
        """
        token = await self._get_token()
        if not token:
            logger.warning("DingTalk directory: no access token")
            return []

        url = f"{self._BASE}/v1.0/contact/users/search"
        payload = {"queryWord": keyword, "offset": 0, "size": min(limit, 50)}

        try:
            resp = await self._http.post(url, json=payload, headers=self._headers(token))
            if resp.status_code != 200:
                body = resp.text[:300]
                logger.warning(
                    "DingTalk user search failed: status={} body={}",
                    resp.status_code, body,
                )
                return []

            data = resp.json()
            user_ids = data.get("list", [])

            # The search API returns a list of user IDs (strings)
            return [
                {
                    "name": f"User ID: {u}",  # We only have ID, no name in this API response
                    "userId": u,
                    "dept": "",
                }
                for u in user_ids if isinstance(u, str)
            ]
        except Exception as e:
            logger.error("DingTalk user search error: {}", e)
            return []

    async def search_groups(self, keyword: str = "", *, limit: int = 20) -> list[dict[str, Any]]:
        """List groups the robot is in, optionally filtered by keyword.

        Returns list of dicts: [{name, openConversationId}, ...]
        Uses: POST /v1.0/robot/groups/query
        Requires permission: 钉钉群基础信息管理权限

        NOTE: If this returns empty or 403, the app needs the "钉钉群基础信息管理权限"
        permission enabled in DingTalk Open Platform.
        """
        token = await self._get_token()
        if not token:
            logger.warning("DingTalk directory: no access token")
            return []

        url = f"{self._BASE}/v1.0/robot/groups/query"
        payload: dict[str, Any] = {"statusCode": 0, "maxResults": min(limit, 100)}

        try:
            resp = await self._http.post(url, json=payload, headers=self._headers(token))
            if resp.status_code == 403:
                logger.warning(
                    "DingTalk group query: 403 Forbidden. "
                    "Please enable '钉钉群基础信息管理权限' for your app in DingTalk Open Platform."
                )
                return []
            if resp.status_code != 200:
                body = resp.text[:300]
                logger.warning(
                    "DingTalk group query failed: status={} body={}",
                    resp.status_code, body,
                )
                return []

            data = resp.json()
            groups = data.get("groupInfos", [])

            # Client-side keyword filter (API doesn't support keyword search natively)
            if keyword:
                kw_lower = keyword.lower()
                groups = [g for g in groups if kw_lower in (g.get("name", "") or "").lower()]

            return [
                {
                    "name": g.get("name", "(unnamed)"),
                    "openConversationId": g.get("openConversationId", ""),
                }
                for g in groups
            ]
        except Exception as e:
            logger.error("DingTalk group query error: {}", e)
            return []
