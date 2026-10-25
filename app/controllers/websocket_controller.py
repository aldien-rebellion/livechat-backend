import json
import logging
import os
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
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
            self.active_connections[workspace_id].remove(websocket)
            if not self.active_connections[workspace_id]:
                del self.active_connections[workspace_id]

    async def update_presence(self, user_id: str, status: str):
        if self.redis_client:
            try:
                await self.redis_client.set(f"presence:{user_id}", status, ex=60)
            except Exception as e:
                logger.warning(f"Failed to update presence in Redis: {e}")

manager = ConnectionManager()

@router.websocket("/ws/{workspace_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, workspace_id: str, user_id: str):
    await manager.connect(workspace_id, websocket)
    await manager.update_presence(user_id, "online")
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "heartbeat":
                await manager.update_presence(user_id, "online")
    except WebSocketDisconnect:
        manager.disconnect(workspace_id, websocket)
        await manager.update_presence(user_id, "offline")
