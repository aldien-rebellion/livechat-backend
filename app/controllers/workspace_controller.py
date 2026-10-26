"""Admin workspace creation and admin/owner content deletion."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.channel import Channel
from app.models.message import Message
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.services.auth_service import get_current_user
from app.services.workspace_service import can_manage_workspace, require_workspace_manager, resolve_workspace, workspace_reference

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


async def workspace_response(db, workspace, user):
    return {
        "id": workspace_reference(workspace), "name": workspace.name,
        "slug": f"workspace-{workspace.id}", "can_manage": await can_manage_workspace(db, user, workspace),
    }


@router.get("")
async def list_workspaces(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    workspaces = await db.scalars(select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.id))
    return [await workspace_response(db, workspace, user) for workspace in workspaces]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: CreateWorkspaceRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Only admins can create workspaces.")
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:workspace_name))"),
        {"workspace_name": payload.name.lower()},
    )
    existing = await db.scalar(select(Workspace).where(func.lower(Workspace.name) == payload.name.lower()))
    if existing is not None:
        raise HTTPException(status_code=409, detail="A workspace with this name already exists or was deleted.")
    workspace = Workspace(name=payload.name, created_by=user.id)
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return await workspace_response(db, workspace, user)


@router.delete("/{workspace_ref}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_ref: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    workspace = await resolve_workspace(db, workspace_ref, lock=True)
    await require_workspace_manager(db, user, workspace)
    deleted_at = datetime.now(timezone.utc)
    # Message content is physically removed; metadata prevents stale-client resurrection.
    await db.execute(delete(Message).where(Message.workspace_id == workspace.id))
    await db.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id))
    await db.execute(update(Channel).where(Channel.workspace_id == workspace.id).values(deleted_at=deleted_at))
    workspace.deleted_at = deleted_at
    await db.commit()
    return Response(status_code=204)
