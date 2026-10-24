
"""Full-text search service for chat messages."""

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


async def search_messages(
    session: AsyncSession,
    channel_id: int,
    query: str,
) -> list[tuple[Message, float]]:
    """Search messages in a channel and return them by relevance.

    Uses the existing PostgreSQL search_vector column and GIN index.
    Returns at most 30 results.
    """
    normalized_query = query.strip()

    if not normalized_query:
        return []

    ts_query = func.plainto_tsquery("simple", normalized_query)
    rank = func.ts_rank(Message.search_vector, ts_query).label("rank")

    statement = (
        select(Message, rank)
        .where(
            Message.channel_id == channel_id,
            Message.search_vector.op("@@")(ts_query),
        )
        .order_by(desc("rank"))
        .limit(30)
    )

    result = await session.execute(statement)

    return [
        (message, float(score))
        for message, score in result.all()
    ]
