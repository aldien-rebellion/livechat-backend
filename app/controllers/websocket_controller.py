import asyncio
import logging
import os
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends
from sqlalchemy import select

from app.db.session import async_session_maker
from app.models.message import Message
from app.models.channel import Channel
from app.models.workspace import Workspace
from app.models.user import User
from app.services.auth_service import authenticate_access_token, get_current_user
from app.services.workspace_service import resolve_workspace

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])


async def active_channel(db, workspace, channel_ref):
    if channel_ref.isdigit():
        channel = await db.get(Channel, int(channel_ref))
    else:
        channel = await db.scalar(select(Channel).where(Channel.workspace_id == workspace.id, Channel.name == channel_ref))
    if channel is None or channel.workspace_id != workspace.id or channel.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Channel not found.")
    return channel


async def save_message_to_db(workspace_ref: str, channel_ref: str, user_id_val: str, content: str):
    """Persist only existing active rooms; never recreate deleted directories."""
    if not user_id_val.isdigit() or not isinstance(content, str) or not content.strip():
        return None
    try:
        async with async_session_maker() as db:
            user = await db.get(User, int(user_id_val))
            if user is None:
                return None
            workspace = await resolve_workspace(db, workspace_ref, lock=True)
            channel = await active_channel(db, workspace, channel_ref)
            message = Message(workspace_id=workspace.id, channel_id=channel.id, user_id=user.id, content=content.strip())
            db.add(message)
            await db.commit()
            await db.refresh(message)
            return {
                "id": str(message.id), "channel_id": str(channel.id), "user_id": str(user.id),
                "content": message.content, "created_at": message.created_at.isoformat(),
                "author": {"id": str(user.id), "full_name": user.username},
            }
    except HTTPException:
        return None
    except Exception as exc:
        logger.warning("Could not persist message to DB: %s", exc)
        return None

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

    async def broadcast_all(self, message: dict, sender: WebSocket = None):
        """Broadcast message to all connected clients across all workspaces."""
        for ws_key in list(self.active_connections.keys()):
            for connection in list(self.active_connections.get(ws_key, [])):
                if connection != sender:
                    try:
                        await connection.send_json(message)
                    except Exception:
                        self.disconnect(ws_key, connection)

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
    try:
        async with async_session_maker() as db:
            user = await authenticate_access_token(db, token or "")
            await resolve_workspace(db, effective_workspace)
            effective_user = str(user.id)
            effective_name = user.username
    except HTTPException:
        await websocket.close(code=4401)
        return
    await manager.connect(effective_workspace, websocket)
    await manager.update_presence(effective_user, "online")
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action") or data.get("type")
            if action == "heartbeat":
                await manager.update_presence(effective_user, "online")
            elif action == "subscribe":
                logger.info("User %s subscribed to channel %s", effective_user, data.get("channel_id"))
            elif action == "typing":
                try:
                    async with async_session_maker() as db:
                        await authenticate_access_token(db, token or "")
                        workspace = await resolve_workspace(db, effective_workspace)
                        channel = await active_channel(db, workspace, str(data.get("channel_id", "")))
                        channel_id = str(channel.id)
                    await manager.broadcast(effective_workspace, {
                        "type": "user_typing", "workspaceId": effective_workspace, "channelId": channel_id,
                        "userId": effective_user, "name": effective_name,
                    }, sender=websocket)
                except HTTPException:
                    continue
            elif action == "send_message":
                try:
                    async with async_session_maker() as db:
                        await authenticate_access_token(db, token or "")
                except HTTPException:
                    await websocket.close(code=4401)
                    break
                message = await save_message_to_db(
                    effective_workspace, str(data.get("channel_id", "")), effective_user, data.get("content", "")
                )
                if message is None:
                    await websocket.send_json({"type": "error", "message": "Channel unavailable. Message was not sent."})
                    continue
                await manager.broadcast(effective_workspace, {
                    "type": "new_message", "workspaceId": effective_workspace, "message": message,
                })
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(effective_workspace, websocket)
        await manager.update_presence(effective_user, "offline")


@router.get("/channels/{channel_id}/messages")
@router.get("/api/v1/channels/{channel_id}/messages")
async def get_channel_messages(channel_id: str, limit: int = 50, user: User = Depends(get_current_user)):
    """Retrieve recent content only from an active channel and workspace."""
    try:
        async with async_session_maker() as db:
            channel_filter = Channel.id == int(channel_id) if channel_id.isdigit() else Channel.name == channel_id
            channel = await db.scalar(select(Channel).join(Workspace).where(
                channel_filter, Channel.deleted_at.is_(None), Workspace.deleted_at.is_(None),
            ))
            if channel is None:
                return []
            result = await db.scalars(select(Message).where(Message.channel_id == channel.id)
                                      .order_by(Message.created_at.desc()).limit(max(1, min(limit, 100))))
            messages = list(result.all())
            messages.reverse()
            user_ids = {message.user_id for message in messages}
            users = await db.scalars(select(User).where(User.id.in_(user_ids))) if user_ids else []
            names = {user.id: user.username or user.email.split("@")[0] for user in users}
            return [{
                "id": str(message.id), "channel_id": str(channel.id), "workspace_id": str(message.workspace_id),
                "user_id": str(message.user_id), "content": message.content,
                "created_at": message.created_at.isoformat() if message.created_at else "",
                "author": {"id": str(message.user_id), "full_name": names.get(message.user_id, f"User {message.user_id}")},
            } for message in messages]
    except Exception as exc:
        logger.warning("Error fetching channel messages: %s", exc)
        return []
