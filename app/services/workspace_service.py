"""Authoritative workspace lookup and shared transaction locks."""
from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember

WORKSPACE_NAMES = {
    "team": "Live Chat Team",
    "design": "Design Studio",
    "new": "New Workspace",
}


def workspace_reference(workspace):
    return next((ref for ref, name in WORKSPACE_NAMES.items() if name == workspace.name), str(workspace.id))


async def can_manage_workspace(db, user, workspace):
    if getattr(user, "is_admin", False) or workspace.created_by == user.id:
        return True
    member = await db.scalar(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == user.id,
        WorkspaceMember.role == "admin",
    ))
    return member is not None


async def require_workspace_manager(db, user, workspace):
    if not await can_manage_workspace(db, user, workspace):
        raise HTTPException(status_code=403, detail="Only an admin or workspace owner can delete this resource.")


async def lock_workspace(db, workspace):
    # All directory and message writers serialize through this lock across workers.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :workspace_id)"),
        {"namespace": 1128812108, "workspace_id": workspace.id},
    )
    await db.refresh(workspace)
    if workspace.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Workspace has been deleted.")


async def resolve_workspace(db, workspace_ref: str, *, lock: bool = False):
    if workspace_ref.isdigit():
        workspace = await db.get(Workspace, int(workspace_ref))
    else:
        name = WORKSPACE_NAMES.get(workspace_ref)
        if name is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        workspace = await db.scalar(select(Workspace).where(Workspace.name == name))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if workspace.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Workspace has been deleted.")
    if lock:
        await lock_workspace(db, workspace)
    return workspace
