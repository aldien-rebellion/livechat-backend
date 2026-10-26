"""Search endpoint contracts use authenticated callers and no external database."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.controllers.search_controller import router
from app.db.session import get_db
from app.services.auth_service import get_current_user


@pytest.fixture(autouse=True)
def init_test_database():
    """Only this endpoint module replaces the external-database fixture."""


@pytest.fixture
def search_api():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(router)
    db = AsyncMock()

    async def session_override():
        yield db

    app.dependency_overrides[get_db] = session_override
    return app, db


@pytest.mark.asyncio
async def test_search_api_endpoints(search_api):
    app, db = search_api
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2, is_admin=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ["/api/v1/channels/abc/search?q=test", "/api/v1/channels/1/search?q=", "/channels/1/search?q="]:
            response = await client.get(path)
            assert response.status_code == 200
            assert response.json() == []
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["/api/v1", ""])
async def test_anonymous_search_is_rejected(search_api, prefix):
    app, db = search_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"{prefix}/channels/1/search?q=hello")
    assert response.status_code == 401
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_query_excludes_deleted_channels_and_workspaces(search_api):
    app, db = search_api
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2, is_admin=False)
    db.execute.return_value = MagicMock(all=MagicMock(return_value=[]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/channels/10/search?q=hello")
    assert response.status_code == 200
    assert response.json() == []
    statement = db.execute.await_args.args[0]
    sql = str(statement)
    assert "channels.deleted_at IS NULL" in sql
    assert "workspaces.deleted_at IS NULL" in sql
    assert statement.compile().params["channel_id_1"] == 10
