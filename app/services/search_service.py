
"""Full-text search service for chat messages."""

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.channel import Channel
from app.models.workspace import Workspace


async def search_messages(
    session: AsyncSession,
    channel_id: int,
    query: str,
) -> list[tuple[Message, float]]:
    """Find full-text or literal substring matches in one active channel.

    Literal matching also supports partial words and unsegmented Thai text.
    SQL wildcard characters are escaped rather than interpreted as patterns.
    """
    normalized_query = query.strip()

    if not normalized_query:
        return []

    ts_query = func.plainto_tsquery("simple", normalized_query)
    rank = func.coalesce(func.ts_rank(Message.search_vector, ts_query), 0).label("rank")

    statement = (
        select(Message, rank)
        .join(Channel, Channel.id == Message.channel_id)
        .join(Workspace, Workspace.id == Message.workspace_id)
        .where(
            Message.channel_id == channel_id,
            Channel.deleted_at.is_(None),
            Workspace.deleted_at.is_(None),
            or_(
                Message.search_vector.op("@@")(ts_query),
                func.lower(Message.content).contains(normalized_query.lower(), autoescape=True),
            ),
        )
        .order_by(desc("rank"), Message.created_at.desc(), Message.id.desc())
        .limit(30)
    )

    result = await session.execute(statement)

    return [
        (message, float(score))
        for message, score in result.all()
    ]
