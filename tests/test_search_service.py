import secrets
from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from app.services.search_service import search_messages
from app.db.session import async_session_maker
from app.models.user import User
from app.models.workspace import Workspace
from app.models.channel import Channel
from app.models.message import Message


@pytest.mark.asyncio
async def test_search_messages_empty_query():
    """Empty or whitespace-only query should immediately return [] without DB query."""
    async with async_session_maker() as session:
        res = await search_messages(session, channel_id=1, query="")
        assert res == []
        res_ws = await search_messages(session, channel_id=1, query="   ")
        assert res_ws == []


@pytest.mark.asyncio
async def test_search_messages_integration_with_db():
    """Test full-text search against PostgreSQL with real records and tsvector."""
    async with async_session_maker() as session:
        rand_suffix = secrets.token_hex(4)
        # Create test user
        user = User(
            email=f"search_user_{rand_suffix}@example.com",
            username=f"search_user_{rand_suffix}",
            hashed_password="test_hashed_password",
        )
        session.add(user)
        await session.flush()

        # Create workspace
        ws = Workspace(
            name=f"Search Test WS {rand_suffix}",
            created_by=user.id,
        )
        session.add(ws)
        await session.flush()

        # Create channels
        ch1 = Channel(
            workspace_id=ws.id,
            name="general",
        )
        ch2 = Channel(
            workspace_id=ws.id,
            name="random",
        )
        session.add_all([ch1, ch2])
        await session.flush()

        # Create messages in ch1 and ch2
        msg1 = Message(
            workspace_id=ws.id,
            channel_id=ch1.id,
            user_id=user.id,
            content="Deploying the new Kubernetes microservice to production",
        )
        msg2 = Message(
            workspace_id=ws.id,
            channel_id=ch1.id,
            user_id=user.id,
            content="PostgreSQL full text search is blazing fast with tsvector",
        )
        msg3 = Message(
            workspace_id=ws.id,
            channel_id=ch2.id,
            user_id=user.id,
            content="Kubernetes in another channel should not be found in channel 1",
        )
        session.add_all([msg1, msg2, msg3])
        await session.flush()

        # Populate search_vector using to_tsvector
        await session.execute(
            text(
                "UPDATE messages SET search_vector = to_tsvector('simple', content) WHERE id IN (:m1, :m2, :m3)"
            ),
            {"m1": msg1.id, "m2": msg2.id, "m3": msg3.id},
        )
        await session.commit()

        # Search in channel 1 for 'Kubernetes'
        results_k8s = await search_messages(session, channel_id=ch1.id, query="Kubernetes")
        assert len(results_k8s) == 1
        found_msg, rank = results_k8s[0]
        assert found_msg.id == msg1.id
        assert "Kubernetes" in found_msg.content
        assert rank > 0

        # Search in channel 1 for 'PostgreSQL'
        results_pg = await search_messages(session, channel_id=ch1.id, query="PostgreSQL")
        assert len(results_pg) == 1
        assert results_pg[0][0].id == msg2.id

        # Search for non-existent word
        results_none = await search_messages(session, channel_id=ch1.id, query="UnicornElephant")
        assert len(results_none) == 0

        # Defense in depth: tombstones hide content even before a purge finishes.
        ch1.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        assert await search_messages(session, channel_id=ch1.id, query="Kubernetes") == []
        ch1.deleted_at = None
        ws.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        assert await search_messages(session, channel_id=ch1.id, query="Kubernetes") == []
