"""Resolve the workspace references used by the sidebar and WebSocket client."""
from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.workspace import Workspace


WORKSPACE_NAMES = {
    "team": "Live Chat Team",
    "design": "Design Studio",
    "new": "New Workspace",
}


async def resolve_workspace(db, workspace_ref: str, created_by: int | None = None):
    if workspace_ref.isdigit():
        workspace = await db.get(Workspace, int(workspace_ref))
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        return workspace

    name = WORKSPACE_NAMES.get(workspace_ref)
    if name is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    if created_by is not None:
        # Serialize first creation across API workers, not just within one process.
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:workspace_name))"),
            {"workspace_name": name},
        )
    workspace = await db.scalar(select(Workspace).where(Workspace.name == name))
    if workspace is None and created_by is not None:
        workspace = Workspace(name=name, created_by=created_by)
        db.add(workspace)
        await db.flush()
    return workspace
