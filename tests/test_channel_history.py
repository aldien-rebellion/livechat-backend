"""History requests must never fall back to messages from other channels."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.controllers import websocket_controller as controller


@pytest.fixture(autouse=True)
def init_test_database():
    """These query regression tests use a fake session and need no database."""


@pytest.fixture
def history_db(monkeypatch):
    db = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(controller, "async_session_maker", lambda: context)
    return db


@pytest.mark.asyncio
async def test_new_channel_has_empty_history_without_querying_messages(history_db):
    history_db.scalar.return_value = None

    assert await controller.get_channel_messages("new-channel-uuid") == []
    history_db.scalars.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_ref,resolved_id", [("general", 7), ("42", 42), ("0", 0)])
async def test_history_query_always_filters_by_resolved_channel(history_db, channel_ref, resolved_id):
    history_db.scalar.return_value = SimpleNamespace(id=resolved_id)
    history_db.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

    assert await controller.get_channel_messages(channel_ref) == []

    statement = history_db.scalars.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "WHERE messages.channel_id =" in str(compiled)
    assert compiled.params["channel_id_1"] == resolved_id
    if channel_ref.isdigit():
        history_db.scalar.assert_not_awaited()
