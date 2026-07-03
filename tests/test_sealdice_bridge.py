import pytest

from data.plugins.astrbot_plugin_sealdice_core.go_bridge import (
    BridgeMessage,
    SeaDiceHTTPBridge,
)


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class FakeClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append(("post", url, headers or {}, json or {}))
        if url.endswith("/sd-api/signin"):
            return FakeResponse({"token": "token-1"})
        return FakeResponse({"ok": True})

    async def get(self, url, headers=None):
        self.calls.append(("get", url, headers or {}, None))
        return FakeResponse({"messages": [{"message": "1d6 = 4"}]})


@pytest.mark.asyncio
async def test_go_bridge_signs_in_executes_and_reads_recent_messages():
    client = FakeClient()
    bridge = SeaDiceHTTPBridge(
        "http://127.0.0.1:3211",
        password="pw",
        client_factory=lambda: client,
    )

    replies = await bridge.execute(
        BridgeMessage(
            content=".r 1d6",
            group_id="g1",
            user_id="u1",
            sender_name="调查员",
        ),
    )

    assert replies == ["1d6 = 4"]
    assert client.calls[0][0] == "post"
    assert client.calls[0][1].endswith("/sd-api/signin")
    assert client.calls[1][1].endswith("/sd-api/dice/exec")
    assert client.calls[1][2]["Token"] == "token-1"
    assert client.calls[1][3]["msg"] == ".r 1d6"
    assert client.calls[2][1].endswith("/sd-api/dice/recentMessage")
