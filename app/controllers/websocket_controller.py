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

    async def broadcast(self, workspace_id: str, message: dict):
        if workspace_id in self.active_connections:
            for connection in self.active_connections[workspace_id]:
                await connection.send_json(message)

manager = ConnectionManager()

@router.websocket("/ws/{workspace_id}")
async def websocket_endpoint(websocket: WebSocket, workspace_id: str):
    await manager.connect(workspace_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.broadcast(workspace_id, data)
    except WebSocketDisconnect:
        manager.disconnect(workspace_id, websocket)