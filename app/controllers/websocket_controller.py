import json
import redis.asyncio as redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List

router = APIRouter(tags=["WebSocket & Presence"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)

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

    async def update_presence(self, user_id: str, status: str = "online"):
        # บันทึกสถานะผู้ใช้ลง Redis พร้อมตั้งค่า TTL 60 วินาที
        key = f"presence:{user_id}"
        await self.redis_client.set(key, status, ex=60)

    async def publish_message(self, workspace_id: str, message: dict):
        await self.redis_client.publish(f"workspace:{workspace_id}", json.dumps(message))

manager = ConnectionManager()

@router.websocket("/ws/{workspace_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, workspace_id: str, user_id: str):
    await manager.connect(workspace_id, websocket)
    await manager.update_presence(user_id, "online")
    
    pubsub = manager.redis_client.pubsub()
    await pubsub.subscribe(f"workspace:{workspace_id}")
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # หากเป็นข้อความประเภท Heartbeat ให้ต่ออายุสถานะ Online
            if data.get("type") == "heartbeat":
                await manager.update_presence(user_id, "online")
            else:
                await manager.publish_message(workspace_id, data)
    except WebSocketDisconnect:
        manager.disconnect(workspace_id, websocket)
        await manager.redis_client.set(f"presence:{user_id}", "offline", ex=60)
        await pubsub.unsubscribe(f"workspace:{workspace_id}")