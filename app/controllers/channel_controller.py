"""Persist channels so all clients share the same channel list and IDs."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.channel import Channel
from app.models.user import User
from app.services.workspace_service import resolve_workspace


router = APIRouter(prefix="/workspaces", tags=["Channels"])


class CreateChannelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    user_id: str

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


def channel_response(channel: Channel, workspace_ref: str):
    return {
        "id": str(channel.id),
        "workspace_id": workspace_ref,
        "name": channel.name,
        "is_private": False,
    }


@router.get("/{workspace_ref}/channels")
async def list_channels(workspace_ref: str, db: AsyncSession = Depends(get_db)):
    workspace = await resolve_workspace(db, workspace_ref)
    if workspace is None:
        return []
    channels = await db.scalars(
        select(Channel).where(Channel.workspace_id == workspace.id).order_by(Channel.id)
    )
    return [channel_response(channel, workspace_ref) for channel in channels]


@router.post("/{workspace_ref}/channels", status_code=status.HTTP_201_CREATED)
async def create_channel(
    workspace_ref: str, payload: CreateChannelRequest, db: AsyncSession = Depends(get_db)
):
    if not payload.user_id.isdigit() or int(payload.user_id) < 1:
        raise HTTPException(status_code=422, detail="A valid user ID is required.")
    user = await db.get(User, int(payload.user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    workspace = await resolve_workspace(db, workspace_ref, created_by=user.id)
    # All writers use the same database lock even if their workspace references differ.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :workspace_id)"),
        {"namespace": 1128812108, "workspace_id": workspace.id},
    )
    existing = await db.scalar(
        select(Channel).where(
            Channel.workspace_id == workspace.id,
            func.lower(Channel.name) == payload.name.lower(),
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="A channel with this name already exists.")

    channel = Channel(workspace_id=workspace.id, name=payload.name)
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel_response(channel, workspace_ref)
