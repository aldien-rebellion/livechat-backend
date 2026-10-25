import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.controllers.websocket_controller import ConnectionManager


class MockWebSocket:
    def __init__(self):
        self.sent_messages = []
        self.closed = False

    async def accept(self):
        pass

    async def send_json(self, data):
        if self.closed:
            raise RuntimeError("Connection closed")
        self.sent_messages.append(data)


@pytest.mark.asyncio
async def test_connection_manager_connect_and_disconnect():
    mgr = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()

    await mgr.connect("ws_1", ws1)
    await mgr.connect("ws_1", ws2)
    assert len(mgr.active_connections["ws_1"]) == 2

    mgr.disconnect("ws_1", ws1)
    assert len(mgr.active_connections["ws_1"]) == 1

    mgr.disconnect("ws_1", ws2)
    assert "ws_1" not in mgr.active_connections


@pytest.mark.asyncio
async def test_connection_manager_broadcast_and_sender_exclusion():
    mgr = ConnectionManager()
    sender = MockWebSocket()
    receiver1 = MockWebSocket()
    receiver2 = MockWebSocket()

    await mgr.connect("ws_team", sender)
    await mgr.connect("ws_team", receiver1)
    await mgr.connect("ws_team", receiver2)

    msg = {"type": "chat", "text": "Hello Team"}
    await mgr.broadcast("ws_team", msg, sender=sender)

    # Sender should NOT receive its own broadcast
    assert sender.sent_messages == []
    # Other receivers should receive it
    assert receiver1.sent_messages == [msg]
    assert receiver2.sent_messages == [msg]


@pytest.mark.asyncio
async def test_connection_manager_broadcast_handles_dropped_clients():
    mgr = ConnectionManager()
    live_ws = MockWebSocket()
    dead_ws = MockWebSocket()
    dead_ws.closed = True  # send_json will raise

    await mgr.connect("ws_drop", live_ws)
    await mgr.connect("ws_drop", dead_ws)

    msg = {"type": "ping"}
    await mgr.broadcast("ws_drop", msg)

    assert live_ws.sent_messages == [msg]
    # Dead client should have been disconnected and removed
    assert dead_ws not in mgr.active_connections.get("ws_drop", [])


@pytest.mark.asyncio
async def test_connection_manager_update_presence():
    mgr = ConnectionManager()
    mock_redis = AsyncMock()
    mgr.redis_client = mock_redis

    await mgr.update_presence("user_123", "online")
    mock_redis.set.assert_awaited_once_with("presence:user_123", "online", ex=60)


def test_websocket_endpoint_full_protocol_flow():
    client = TestClient(app)

    with client.websocket_connect("/ws?token=test_token_abc") as ws1:
        with client.websocket_connect("/ws?token=test_token_xyz") as ws2:
            # 1. Heartbeat frame
            ws1.send_json({"action": "heartbeat"})

            # 2. Subscribe frame
            ws1.send_json({"action": "subscribe", "channel_id": "ch_general"})

            # 3. Typing frame - should broadcast to ws2
            ws1.send_json({"action": "typing", "channel_id": "ch_general"})
            typing_event = ws2.receive_json()
            assert typing_event["type"] == "user_typing"
            assert typing_event["channelId"] == "ch_general"

            # 4. Send message frame - should broadcast to ws2
            ws1.send_json({
                "action": "send_message",
                "channel_id": "ch_general",
                "content": "Hello via WebSocket!",
            })
            msg_event = ws2.receive_json()
            assert msg_event["type"] == "new_message"
            assert msg_event["message"]["content"] == "Hello via WebSocket!"
            assert msg_event["message"]["channel_id"] == "ch_general"
