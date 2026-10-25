from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.search_service import search_messages

router = APIRouter(tags=["Search"])


@router.get("/channels/{channel_id}/search")
async def search_channel_messages(
    channel_id: str,
    q: str = Query("", alias="q"),
    db: AsyncSession = Depends(get_db),
):
    """Search messages in a channel using PostgreSQL Full-Text Search tsvector."""
    try:
        cid = int(channel_id)
    except ValueError:
        return []

    results = await search_messages(db, cid, q)
    return [
        {
            "id": str(msg.id),
            "channel_id": str(msg.channel_id),
            "workspace_id": str(msg.workspace_id),
            "user_id": str(msg.user_id),
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else "",
            "rank": float(rank),
        }
        for msg, rank in results
    ]
