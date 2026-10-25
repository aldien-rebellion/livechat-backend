import asyncio
import json
import logging
import os
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        if redis:
            try:
                self.redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
            except Exception as e:
                logger.warning(f"Could not connect to Redis: {e}")
                self.redis_client = None
        else:
            self.redis_client = None

    async def connect(self, workspace_id: str, websocket: WebSocket):
        await websocket.accept()
        if workspace_id not in self.active_connections:
            self.active_connections[workspace_id] = []
        self.active_connections[workspace_id].append(websocket)

    def disconnect(self, workspace_id: str, websocket: WebSocket):
        if workspace_id in self.active_connections:
            if websocket in self.active_connections[workspace_id]:
                self.active_connections[workspace_id].remove(websocket)
            if not self.active_connections[workspace_id]:
                del self.active_connections[workspace_id]

    async def broadcast(self, workspace_id: str, message: dict, sender: WebSocket = None):
        if workspace_id in self.active_connections:
            for connection in list(self.active_connections[workspace_id]):
                if connection != sender:
                    try:
                        await connection.send_json(message)
                    except Exception:
                        self.disconnect(workspace_id, connection)

    async def update_presence(self, user_id: str, status: str):
        if self.redis_client and user_id:
            try:
                await asyncio.wait_for(
                    self.redis_client.set(f"presence:{user_id}", status, ex=60),
                    timeout=2.0,
                )
            except Exception as e:
                logger.warning(f"Failed to update presence in Redis: {e}")


manager = ConnectionManager()


@router.websocket("/ws")
@router.websocket("/ws/{workspace_id}/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    workspace_id: str = "default",
    user_id: str = "anonymous",
    token: str | None = Query(None),
):
    # If token is provided, user_id can be inferred or set
    effective_user = user_id if user_id != "anonymous" else (token[:8] if token else "guest")
    effective_workspace = workspace_id

    await manager.connect(effective_workspace, websocket)
    await manager.update_presence(effective_user, "online")

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action") or data.get("type")

            if action == "heartbeat":
                await manager.update_presence(effective_user, "online")
            elif action == "subscribe":
                channel_id = data.get("channel_id")
                logger.info(f"User {effective_user} subscribed to channel {channel_id}")
            elif action == "typing":
                channel_id = data.get("channel_id")
                await manager.broadcast(
                    effective_workspace,
                    {
                        "type": "user_typing",
                        "workspaceId": effective_workspace,
                        "channelId": channel_id,
                        "userId": effective_user,
                        "name": effective_user,
                    },
                    sender=websocket,
                )
            elif action == "send_message":
                channel_id = data.get("channel_id")
                content = data.get("content", "")
                await manager.broadcast(
                    effective_workspace,
                    {
                        "type": "new_message",
                        "workspaceId": effective_workspace,
                        "message": {
                            "id": f"msg_{os.urandom(4).hex()}",
                            "channel_id": channel_id,
                            "user_id": effective_user,
                            "content": content,
                        },
                    },
                    sender=websocket,
                )
    except WebSocketDisconnect:
        manager.disconnect(effective_workspace, websocket)
        await manager.update_presence(effective_user, "offline")
