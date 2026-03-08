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
        # Memory cache for department names to avoid rate limiting
        self._dept_names: dict[int, str] = {}

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

    async def get_department_name(self, dept_id: int | str) -> str:
        """Get department name by ID.
        Uses: GET /topapi/v2/department/get
        """
        try:
            current_id = int(dept_id)
        except (ValueError, TypeError):
            return str(dept_id)

        # 1. Check cache first
        if current_id in self._dept_names:
            return self._dept_names[current_id]

        # 2. Fetch from API
        token = await self._get_token()
        if not token:
            return f"部门({current_id})"

        url = f"https://oapi.dingtalk.com/topapi/v2/department/get?access_token={token}"
        try:
            resp = await self._http.post(url, json={"dept_id": current_id})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("errcode") == 0:
                    result = data.get("result", {})
                    # DingTalk v2.0 API often uses 'name' directly
                    name = result.get("name") or result.get("dept_name")
                    if name:
                        # Normalize "全公司" if returned by API
                        if name == "全公司":
                            name = "总公司"
                        self._dept_names[current_id] = name
                        return name
                else:
                    logger.warning("DingTalk OAPI error for dept {}: {}", current_id, data.get("errmsg"))
        except Exception as e:
            logger.error("Error fetching department name for {}: {}", current_id, e)
        
        return f"部门({current_id})"

    async def get_user_org_path(self, user_id: str) -> str:
        """Get full organization path for a user.
        Uses: GET /topapi/v2/department/listparentbyuser
        Returns: "Dept1/Dept2/Dept3"
        """
        token = await self._get_token()
        if not token:
            return ""

        url = f"https://oapi.dingtalk.com/topapi/v2/department/listparentbyuser?access_token={token}"
        try:
            resp = await self._http.post(url, json={"userid": user_id})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("errcode") == 0:
                    # parent_list is a list of lists (paths from roots to user depts)
                    parent_list = data.get("result", {}).get("parent_list", [])
                    if not parent_list:
                        return ""
                    
                    all_resolved_paths = []

                    for raw_path in parent_list:
                        # Handle both [id1, id2] and {"parent_dept_id_list": [id1, id2]}
                        path_ids_list = []
                        if isinstance(raw_path, list):
                            path_ids_list = raw_path
                        elif isinstance(raw_path, dict) and "parent_dept_id_list" in raw_path:
                            path_ids_list = raw_path["parent_dept_id_list"]
                        else:
                            continue
                        
                        # listparentbyuser returns [leaf, ..., root]
                        path_ids = list(reversed(path_ids_list))
                        
                        names = []
                        for d_id in path_ids:
                            name = await self.get_department_name(d_id)
                            names.append(name)
                        
                        if names:
                            all_resolved_paths.append("/".join(names))
                    
                    if not all_resolved_paths:
                        return ""
                    
                    # Deduplicate and join
                    return " | ".join(list(dict.fromkeys(all_resolved_paths)))
        except Exception as e:
            logger.error("Error fetching org path for {}: {}", user_id, e)
        return ""

    async def get_user_details(self, user_id: str, depth: int = 0) -> dict[str, Any]:
        """Get detailed information for a specific user ID.

        Returns: {name, title, dept, email, manager_name, userId, org_path}
        """
        if depth > 1: # Prevent infinite recursion
            return {}
            
        token = await self._get_token()
        if not token:
            return {}

        # Mode A: Legacy OAPI (Preferred)
        url_legacy = f"https://oapi.dingtalk.com/user/get?access_token={token}&userid={user_id}"
        try:
            resp_l = await self._http.get(url_legacy)
            if resp_l.status_code == 200:
                data_l = resp_l.json()
                if data_l.get("errcode") == 0:
                    logger.info("Successfully fetched user info via legacy OAPI for {}", user_id)
                    details = {
                        "name": data_l.get("name", ""),
                        "title": data_l.get("position", ""),
                        "email": data_l.get("email", ""),
                        "userId": user_id
                    }
                    
                    # Departments: Convert IDs to names and get full path
                    dept_ids = data_l.get("department", [])
                    if dept_ids:
                        details["dept"] = await self.get_department_name(dept_ids[0])
                    else:
                        details["dept"] = ""
                    
                    # Get Org Path (Deterministic)
                    org_path = await self.get_user_org_path(user_id)
                    details["org_path"] = org_path

                    # Try to resolve manager name if ID exists
                    manager_id = data_l.get("managerUserId")
                    if manager_id and manager_id != user_id:
                        manager_info = await self.get_user_details(manager_id, depth=depth+1)
                        details["manager_name"] = manager_info.get("name", manager_id)
                    
                    return details
                else:
                    logger.debug("Legacy OAPI error for {}: {}, trying v1.0...", user_id, data_l.get("errmsg"))
        except Exception as e:
            logger.error("Legacy OAPI error: {}", e)

        # Mode B: New API v1.0 (Fallback)
        url_v1 = f"{self._BASE}/v1.0/contact/users/{user_id}"
        try:
            resp = await self._http.get(url_v1, headers=self._headers(token))
            if resp.status_code == 200:
                data = resp.json()
                details = {
                    "name": data.get("name", ""),
                    "title": data.get("title", ""),
                    "email": data.get("email", ""),
                    "userId": user_id
                }
                dept_ids = data.get("deptIdList", [])
                if dept_ids:
                    details["dept"] = await self.get_department_name(dept_ids[0])
                else:
                    details["dept"] = ""
                
                details["org_path"] = await self.get_user_org_path(user_id)
                return details
        except Exception as e:
            logger.error("DingTalk v1.0 fallback error: {}", e)
            
        return {}
