from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.services.search_service import search_messages
from app.services.auth_service import get_current_user
from app.models.user import User

router = APIRouter(tags=["Search"])


@router.get("/channels/{channel_id}/search")
async def search_channel_messages(
    channel_id: str,
    q: str = Query("", alias="q", max_length=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search messages in a channel using PostgreSQL Full-Text Search tsvector."""
    try:
        cid = int(channel_id)
    except ValueError:
        return []

    results = await search_messages(db, cid, q)
    user_ids = {message.user_id for message, _ in results}
    authors = await db.scalars(select(User).where(User.id.in_(user_ids))) if user_ids else []
    names = {author.id: author.username or author.email.split("@")[0] for author in authors}
    return [
        {
            "id": str(msg.id),
            "channel_id": str(msg.channel_id),
            "workspace_id": str(msg.workspace_id),
            "user_id": str(msg.user_id),
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
            "author": {"id": str(msg.user_id), "full_name": names.get(msg.user_id, f"User {msg.user_id}")},
            "rank": float(rank),
        }
        for msg, rank in results
    ]
