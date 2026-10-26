"""Channel creation is durable and discoverable by a second client."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.channel_controller import router
from app.controllers import websocket_controller
from app.db.session import get_db
from app.models.user import User
from app.services.workspace_service import resolve_workspace


@pytest.fixture(autouse=True)
def init_test_database():
    """All database interactions here use a fake session."""


@pytest.fixture
def channel_api():
    workspace = SimpleNamespace(id=5, name="Live Chat Team")
    user = SimpleNamespace(id=3)
    saved = []
    db = AsyncMock()
    db.add = MagicMock(side_effect=saved.append)
    db.get.side_effect = lambda model, key: user if model is User and key == 3 else None

    async def scalar(statement):
        params = statement.compile().params
        if "name_1" in params:
            return workspace if params["name_1"] == "Live Chat Team" else None
        wanted = params.get("lower_1")
        return next((channel for channel in saved if channel.name.lower() == wanted), None)

    db.scalar.side_effect = scalar
    db.scalars.side_effect = lambda statement: list(saved)

    async def refresh(channel):
        channel.id = 17

    db.refresh.side_effect = refresh
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def session_override():
        yield db

    app.dependency_overrides[get_db] = session_override
    return app, db, saved


def test_created_channel_is_available_to_another_client_and_after_reload(channel_api):
    app, db, saved = channel_api
    with TestClient(app) as creator, TestClient(app) as friend:
        response = creator.post(
            "/api/v1/workspaces/team/channels", json={"name": "  homework  ", "user_id": "3"}
        )
        assert response.status_code == 201
        expected = {"id": "17", "workspace_id": "team", "name": "homework", "is_private": False}
        assert response.json() == expected
        assert friend.get("/api/v1/workspaces/team/channels").json() == [expected]
    with TestClient(app) as reloaded:
        assert reloaded.get("/api/v1/workspaces/team/channels").json() == [expected]
    assert len(saved) == 1
    db.commit.assert_awaited_once()


def test_duplicate_channel_name_is_rejected_case_insensitively(channel_api):
    app, db, _ = channel_api
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/workspaces/team/channels", json={"name": "homework", "user_id": "3"}
        ).status_code == 201
        assert client.post(
            "/api/v1/workspaces/team/channels", json={"name": " HOMEWORK ", "user_id": "3"}
        ).status_code == 409
    db.commit.assert_awaited_once()


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_channel_name_is_rejected(channel_api, name):
    app, db, _ = channel_api
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/workspaces/team/channels", json={"name": name, "user_id": "3"}
        ).status_code == 422
    db.commit.assert_not_awaited()


def test_creation_requires_existing_user(channel_api):
    app, db, _ = channel_api
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/workspaces/team/channels", json={"name": "test", "user_id": "999"}
        ).status_code == 404
    db.commit.assert_not_awaited()


def test_missing_known_workspace_has_empty_list_without_creating_records(channel_api):
    app, db, saved = channel_api
    with TestClient(app) as client:
        assert client.get("/api/v1/workspaces/design/channels").json() == []
        assert client.get("/api/v1/workspaces/unknown/channels").status_code == 404
    assert saved == []
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("ref,name", [("design", "Design Studio"), ("new", "New Workspace")])
async def test_workspace_alias_creates_the_correct_workspace(ref, name):
    db = AsyncMock()
    db.add = MagicMock()
    db.scalar.return_value = None
    workspace = await resolve_workspace(db, ref, created_by=3)
    assert workspace.name == name
    assert workspace.created_by == 3
    db.add.assert_called_once_with(workspace)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_numeric_channel_from_another_workspace_is_not_persisted(monkeypatch):
    db = AsyncMock()
    db.add = MagicMock()
    db.get.side_effect = lambda model, key: (
        SimpleNamespace(id=3) if model is User else SimpleNamespace(id=17, workspace_id=999)
    )
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(websocket_controller, "async_session_maker", lambda: context)
    monkeypatch.setattr(
        websocket_controller, "resolve_workspace", AsyncMock(return_value=SimpleNamespace(id=5))
    )
    await websocket_controller.save_message_to_db("team", "17", "3", "wrong workspace")
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
