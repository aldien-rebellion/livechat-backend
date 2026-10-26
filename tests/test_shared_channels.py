"""Shared channels remain discoverable through authenticated directory calls."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.channel_controller import router
from app.db.session import get_db
from app.services.auth_service import get_current_user
from tests.test_directory_management import DirectoryDB


@pytest.fixture(autouse=True)
def init_test_database():
    """Tests use a fake session."""


@pytest.fixture
def channel_api():
    db = DirectoryDB()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def session_override():
        yield db

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2, is_admin=False)
    return app, db


def test_created_channel_is_available_to_another_client_and_after_reload(channel_api):
    app, db = channel_api
    with TestClient(app) as creator, TestClient(app) as friend:
        response = creator.post("/api/v1/workspaces/team/channels", json={"name": "  homework  "})
        assert response.status_code == 201
        expected = {"id": "100", "workspace_id": "team", "name": "homework", "is_private": False}
        assert response.json() == expected
        assert expected in friend.get("/api/v1/workspaces/team/channels").json()
    with TestClient(app) as reloaded:
        assert expected in reloaded.get("/api/v1/workspaces/team/channels").json()
    assert db.commits == 1


def test_duplicate_channel_name_is_rejected_case_insensitively(channel_api):
    app, db = channel_api
    with TestClient(app) as client:
        assert client.post("/api/v1/workspaces/team/channels", json={"name": "homework"}).status_code == 201
        assert client.post("/api/v1/workspaces/team/channels", json={"name": " HOMEWORK "}).status_code == 409
    assert db.commits == 1


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_channel_name_is_rejected(channel_api, name):
    app, db = channel_api
    with TestClient(app) as client:
        assert client.post("/api/v1/workspaces/team/channels", json={"name": name}).status_code == 422
    assert db.commits == 0


def test_members_cannot_implicitly_create_missing_workspaces(channel_api):
    app, db = channel_api
    with TestClient(app) as client:
        assert client.get("/api/v1/workspaces/design/channels").status_code == 404
        assert client.post("/api/v1/workspaces/design/channels", json={"name": "test"}).status_code == 404
    assert db.commits == 0
