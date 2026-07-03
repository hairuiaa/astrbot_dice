from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


class SeaDiceBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class BridgeMessage:
    content: str
    message_type: str = "group"
    group_id: str = ""
    user_id: str = ""
    sender_name: str = ""


class SeaDiceHTTPBridge:
    def __init__(
        self,
        base_url: str,
        *,
        password: str = "",
        token: str = "",
        timeout: float = 5.0,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.password = password
        self.token = token
        self.timeout = timeout
        self._client_factory = client_factory

    async def signin(self) -> str:
        payload = {"password": self.password}
        data = await self._request_json("post", "/sd-api/signin", json=payload)
        token = data.get("token") or data.get("data", {}).get("token")
        if not token:
            raise SeaDiceBridgeError("SeaDice bridge did not return a token.")
        self.token = str(token)
        return self.token

    async def execute(self, message: BridgeMessage) -> list[str]:
        if not self.token:
            await self.signin()
        await self.send_message(message)
        return await self.recent_messages()

    async def send_message(self, message: BridgeMessage, split_len: int = 0) -> None:
        payload = {
            "msg": message.content,
            "messageType": message.message_type,
            "groupId": message.group_id,
            "userId": message.user_id,
            "nickname": message.sender_name,
            "splitLen": split_len,
        }
        await self._request_json("post", "/sd-api/dice/exec", json=payload)

    async def recent_messages(self) -> list[str]:
        data = await self._request_json("get", "/sd-api/dice/recentMessage")
        if isinstance(data, list):
            return [self._message_text(item) for item in data]
        messages = data.get("messages") or data.get("data") or data.get("items") or []
        if isinstance(messages, str):
            return [messages]
        if not isinstance(messages, list):
            return []
        return [self._message_text(item) for item in messages]

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Token"] = self.token
        close_client = self._client_factory is None
        client = (
            httpx.AsyncClient(timeout=self.timeout)
            if close_client
            else self._client_factory()
        )
        try:
            request = getattr(client, method)
            response = await request(self.base_url + path, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        finally:
            if close_client:
                await client.aclose()

    def _message_text(self, item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            for key in ("message", "msg", "content", "text"):
                value = item.get(key)
                if value:
                    return str(value)
        return str(item)
