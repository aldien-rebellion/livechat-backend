import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from app.db.session import async_session_maker
from app.models.message import Message
from app.models.workspace import Workspace
from app.models.channel import Channel

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])


async def save_message_to_db(workspace_ref: str, channel_ref: str, user_id_val: str, content: str):
    """Safely persist a chat message into PostgreSQL in background."""
    try:
        async with async_session_maker() as db:
            # 1. Resolve or create workspace
            ws = None
            if workspace_ref.isdigit():
                ws = await db.get(Workspace, int(workspace_ref))
            if not ws:
                ws = await db.scalar(select(Workspace).where(Workspace.name == "Live Chat Team"))
            if not ws:
                ws = Workspace(name="Live Chat Team", created_by=1)
                db.add(ws)
                await db.commit()
                await db.refresh(ws)

            # 2. Resolve or create channel
            ch = None
            if channel_ref.isdigit():
                ch = await db.get(Channel, int(channel_ref))
            if not ch:
                ch = await db.scalar(
                    select(Channel).where(Channel.workspace_id == ws.id, Channel.name == channel_ref)
                )
            if not ch:
                ch = Channel(workspace_id=ws.id, name=channel_ref if not channel_ref.isdigit() else "general")
                db.add(ch)
                await db.commit()
                await db.refresh(ch)

            # 3. Resolve user_id
            uid = int(user_id_val) if user_id_val.isdigit() else 1

            # 4. Save message
            msg = Message(
                workspace_id=ws.id,
                channel_id=ch.id,
                user_id=uid,
                content=content,
            )
            db.add(msg)
            await db.commit()
    except Exception as e:
        logger.warning(f"Could not persist message to DB: {e}")


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
    workspace_id_param: str | None = Query(None, alias="workspace_id"),
    user_id_param: str | None = Query(None, alias="user_id"),
    user_name_param: str | None = Query(None, alias="user_name"),
):
    effective_workspace = workspace_id_param or workspace_id
    effective_user = user_id_param or (user_id if user_id != "anonymous" else (token[:8] if token else "guest"))
    effective_name = user_name_param or effective_user

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
                        "userId": str(effective_user),
                        "name": effective_name,
                    },
                    sender=websocket,
                )
            elif action == "send_message":
                channel_id = data.get("channel_id")
                content = data.get("content", "")
                created_at_iso = datetime.now(timezone.utc).isoformat()
                msg_id = f"msg_{os.urandom(6).hex()}"

                message_payload = {
                    "type": "new_message",
                    "workspaceId": effective_workspace,
                    "message": {
                        "id": msg_id,
                        "channel_id": channel_id,
                        "user_id": str(effective_user),
                        "content": content,
                        "created_at": created_at_iso,
                        "author": {
                            "id": str(effective_user),
                            "full_name": effective_name,
                        },
                    },
                }

                # Broadcast to all connected clients in this workspace (including sender)
                await manager.broadcast(
                    effective_workspace,
                    message_payload,
                    sender=None,
                )

                # Persist to database in background
                asyncio.create_task(
                    save_message_to_db(effective_workspace, channel_id, str(effective_user), content)
                )
    except WebSocketDisconnect:
        manager.disconnect(effective_workspace, websocket)
        await manager.update_presence(effective_user, "offline")


@router.get("/channels/{channel_id}/messages")
@router.get("/api/v1/channels/{channel_id}/messages")
async def get_channel_messages(channel_id: str, limit: int = 50):
    """Retrieve recent messages for a channel."""
    try:
        async with async_session_maker() as db:
            cid = int(channel_id) if channel_id.isdigit() else None
            stmt = select(Message)
            if cid:
                stmt = stmt.where(Message.channel_id == cid)
            stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
            result = await db.scalars(stmt)
            messages = list(result.all())
            messages.reverse()
            return [
                {
                    "id": str(msg.id),
                    "channel_id": str(msg.channel_id),
                    "workspace_id": str(msg.workspace_id),
                    "user_id": str(msg.user_id),
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else "",
                    "author": {
                        "id": str(msg.user_id),
                        "full_name": f"User {msg.user_id}",
                    },
                }
                for msg in messages
            ]
    except Exception as e:
        logger.warning(f"Error fetching channel messages: {e}")
        return []
