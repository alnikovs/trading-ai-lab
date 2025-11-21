from __future__ import annotations

from typing import Dict, Any, Optional

import httpx


class CursorClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.cursor.com",
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            auth=(self.api_key, ""),
            timeout=self.timeout,
        )

    async def list_agents(
        self, limit: int = 20, cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        resp = await self._client.get(f"{self.base_url}/v0/agents", params=params)
        resp.raise_for_status()
        return resp.json()

    async def launch_agent(
        self,
        prompt_text: str,
        repository: str,
        ref: str = "main",
        auto_create_pr: bool = True,
        branch_name: Optional[str] = None,
        model: Optional[str] = None,
        webhook_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "prompt": {
                "text": prompt_text,
            },
            "source": {
                "repository": repository,
                "ref": ref,
            },
            "target": {
                "autoCreatePr": auto_create_pr,
            },
        }

        if branch_name:
            payload["target"]["branchName"] = branch_name

        if model:
            payload["model"] = model

        if webhook_url:
            webhook_payload: Dict[str, Any] = {
                "url": webhook_url,
            }
            if webhook_secret:
                webhook_payload["secret"] = webhook_secret
            payload["webhook"] = webhook_payload

        resp = await self._client.post(f"{self.base_url}/v0/agents", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_agent(self, agent_id: str) -> Dict[str, Any]:
        resp = await self._client.get(f"{self.base_url}/v0/agents/{agent_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_conversation(self, agent_id: str) -> Dict[str, Any]:
        resp = await self._client.get(f"{self.base_url}/v0/agents/{agent_id}/conversation")
        resp.raise_for_status()
        return resp.json()

    async def add_followup(self, agent_id: str, text: str) -> Dict[str, Any]:
        payload = {
            "prompt": {
                "text": text,
            },
        }
        resp = await self._client.post(
            f"{self.base_url}/v0/agents/{agent_id}/followup", json=payload
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

