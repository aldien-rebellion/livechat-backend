"""Shared channels, authenticated creation and admin/owner deletion."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.channel import Channel
from app.models.message import Message
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.workspace_service import resolve_workspace, require_workspace_manager

router = APIRouter(prefix="/workspaces", tags=["Channels"])


class CreateChannelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # Older clients send this; identity always comes from the bearer token.
    user_id: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


def channel_response(channel: Channel, workspace_ref: str):
    return {"id": str(channel.id), "workspace_id": workspace_ref, "name": channel.name, "is_private": False}


@router.get("/{workspace_ref}/channels")
async def list_channels(
    workspace_ref: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    workspace = await resolve_workspace(db, workspace_ref)
    channels = await db.scalars(
        select(Channel).where(Channel.workspace_id == workspace.id, Channel.deleted_at.is_(None)).order_by(Channel.id)
    )
    return [channel_response(channel, workspace_ref) for channel in channels]


@router.post("/{workspace_ref}/channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    workspace_ref: str, payload: CreateChannelRequest, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await resolve_workspace(db, workspace_ref, lock=True)
    existing = await db.scalar(
        select(Channel).where(Channel.workspace_id == workspace.id, func.lower(Channel.name) == payload.name.lower())
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="A channel with this name already exists or was deleted.")
    channel = Channel(workspace_id=workspace.id, name=payload.name)
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel_response(channel, workspace_ref)


@router.delete("/{workspace_ref}/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    workspace_ref: str, channel_id: int, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await resolve_workspace(db, workspace_ref, lock=True)
    await require_workspace_manager(db, user, workspace)
    channel = await db.get(Channel, channel_id)
    if channel is None or channel.workspace_id != workspace.id or channel.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Channel not found.")
    await db.execute(delete(Message).where(Message.channel_id == channel.id, Message.workspace_id == workspace.id))
    channel.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=204)
