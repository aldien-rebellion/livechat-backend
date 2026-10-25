from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List

router = APIRouter(tags=["WebSocket"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

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
        # บันทึกสถานะ Online/Offline ลง Redis พร้อม TTL 60 วินาที
        pass

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
