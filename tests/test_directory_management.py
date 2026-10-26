"""Workspace roles, content deletion, and stale-client protection."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Delete, Update

from app.controllers import channel_controller, workspace_controller, websocket_controller, search_controller
from app.db.session import get_db
from app.models.channel import Channel
from app.models.message import Message
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.services.auth_service import get_current_user
from app.services.workspace_service import resolve_workspace


@pytest.fixture(autouse=True)
def init_test_database():
    """Tests use a deterministic in-memory session rather than external services."""


class DirectoryDB:
    def __init__(self):
        self.workspace = Workspace(id=5, name="Live Chat Team", created_by=1)
        self.channel = Channel(id=10, workspace_id=5, name="general")
        self.other = Channel(id=11, workspace_id=9, name="other")
        self.records = {
            Workspace: [self.workspace], Channel: [self.channel, self.other], WorkspaceMember: [],
            User: [SimpleNamespace(id=1, username="owner"), SimpleNamespace(id=2, username="member")],
            Message: [SimpleNamespace(id=30, workspace_id=5, channel_id=10),
                      SimpleNamespace(id=31, workspace_id=9, channel_id=11)],
        }
        self.commits = 0
        self.executed = []

    def add(self, row):
        self.records[type(row)].append(row)

    async def get(self, model, key):
        return next((row for row in self.records[model] if row.id == key), None)

    async def refresh(self, row):
        if row.id is None:
            row.id = 100
        if isinstance(row, Message) and row.created_at is None:
            row.created_at = datetime.now(timezone.utc)

    async def commit(self):
        self.commits += 1

    async def scalar(self, statement):
        rows = await self.scalars(statement)
        return next(iter(rows), None)

    async def scalars(self, statement):
        model = statement.column_descriptions[0]["entity"]
        params = statement.compile().params
        rows = self.records[model]
        if "workspace_id_1" in params:
            rows = [row for row in rows if row.workspace_id == params["workspace_id_1"]]
        if "user_id_1" in params:
            rows = [row for row in rows if row.user_id == params["user_id_1"]]
        if "role_1" in params:
            rows = [row for row in rows if row.role == params["role_1"]]
        if "id_1" in params:
            rows = [row for row in rows if row.id == params["id_1"]]
        if "name_1" in params:
            rows = [row for row in rows if row.name == params["name_1"]]
        if "lower_1" in params:
            rows = [row for row in rows if row.name.lower() == params["lower_1"]]
        if "deleted_at IS NULL" in str(statement):
            rows = [row for row in rows if row.deleted_at is None]
        return list(rows)

    async def execute(self, statement, params=None):
        self.executed.append(statement)
        if isinstance(statement, (Delete, Update)):
            model = {"messages": Message, "workspace_members": WorkspaceMember, "channels": Channel}[statement.table.name]
            values = statement.compile().params
            matching = [row for row in self.records[model] if
                        ("workspace_id_1" not in values or row.workspace_id == values["workspace_id_1"]) and
                        ("channel_id_1" not in values or row.channel_id == values["channel_id_1"])]
            if isinstance(statement, Delete):
                self.records[model] = [row for row in self.records[model] if row not in matching]
            else:
                for row in matching:
                    row.deleted_at = values["deleted_at"]


@pytest.fixture
def directory_api():
    db = DirectoryDB()
    identity = {"user": SimpleNamespace(id=2, is_admin=False)}
    app = FastAPI()
    app.include_router(workspace_controller.router, prefix="/api/v1")
    app.include_router(channel_controller.router, prefix="/api/v1")
    app.include_router(websocket_controller.router)
    app.include_router(search_controller.router, prefix="/api/v1")

    async def session_override():
        yield db

    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[get_current_user] = lambda: identity["user"]
    return app, db, identity


def test_member_cannot_create_workspace_even_when_sending_admin_payload(directory_api):
    app, db, _ = directory_api
    with TestClient(app) as client:
        response = client.post("/api/v1/workspaces", json={"name": "New room", "is_admin": True})
    assert response.status_code == 403
    assert db.commits == 0


def test_admin_creates_workspace_and_is_owner(directory_api):
    app, db, identity = directory_api
    identity["user"] = SimpleNamespace(id=8, is_admin=True)
    with TestClient(app) as client:
        response = client.post("/api/v1/workspaces", json={"name": "  Engineering  "})
    assert response.status_code == 201
    assert response.json() == {"id": "100", "name": "Engineering", "slug": "workspace-100", "can_manage": True}
    assert db.records[Workspace][-1].created_by == 8


def test_member_can_create_channel_but_cannot_claim_workspace_ownership(directory_api):
    app, db, _ = directory_api
    with TestClient(app) as client:
        response = client.post("/api/v1/workspaces/team/channels", json={"name": "news", "user_id": "1"})
    assert response.status_code == 201
    assert response.json()["id"] == "100"
    assert db.workspace.created_by == 1


@pytest.mark.parametrize("resource", ["/workspaces/team", "/workspaces/team/channels/10"])
def test_regular_member_cannot_delete(directory_api, resource):
    app, db, _ = directory_api
    with TestClient(app) as client:
        assert client.delete("/api/v1" + resource).status_code == 403
    assert len(db.records[Message]) == 2
    assert db.commits == 0


@pytest.mark.parametrize("role", ["owner", "admin", "workspace_admin"])
def test_authorized_channel_delete_purges_only_its_messages(directory_api, role):
    app, db, identity = directory_api
    identity["user"] = SimpleNamespace(id=1 if role == "owner" else 2, is_admin=role == "admin")
    if role == "workspace_admin":
        db.records[WorkspaceMember].append(WorkspaceMember(id=7, workspace_id=5, user_id=2, role="admin"))
    with TestClient(app) as client:
        assert client.delete("/api/v1/workspaces/team/channels/10").status_code == 204
        assert client.get("/api/v1/workspaces/team/channels").json() == []
    assert [row.id for row in db.records[Message]] == [31]
    assert db.channel.deleted_at is not None
    assert db.other.deleted_at is None


def test_owner_workspace_delete_purges_content_members_and_hides_directory(directory_api):
    app, db, identity = directory_api
    identity["user"] = SimpleNamespace(id=1, is_admin=False)
    db.records[WorkspaceMember].append(WorkspaceMember(id=7, workspace_id=5, user_id=2, role="member"))
    with TestClient(app) as client:
        assert client.delete("/api/v1/workspaces/team").status_code == 204
        assert client.get("/api/v1/workspaces").json() == []
        assert client.post("/api/v1/workspaces/team/channels", json={"name": "revive"}).status_code == 410
    assert [row.id for row in db.records[Message]] == [31]
    assert db.records[WorkspaceMember] == []
    assert db.channel.deleted_at is not None
    assert db.workspace.deleted_at is not None


def test_channel_from_other_workspace_cannot_be_deleted(directory_api):
    app, db, identity = directory_api
    identity["user"] = SimpleNamespace(id=1, is_admin=False)
    with TestClient(app) as client:
        assert client.delete("/api/v1/workspaces/team/channels/11").status_code == 404
    assert len(db.records[Message]) == 2


def test_directory_permissions_come_from_current_identity(directory_api):
    app, db, identity = directory_api
    with TestClient(app) as client:
        assert client.get("/api/v1/workspaces").json()[0]["can_manage"] is False
        identity["user"] = SimpleNamespace(id=1, is_admin=False)
        assert client.get("/api/v1/workspaces").json()[0]["can_manage"] is True


def test_missing_auth_is_rejected_before_directory_mutation(directory_api):
    app, db, _ = directory_api
    app.dependency_overrides.pop(get_current_user)
    with TestClient(app) as client:
        assert client.post("/api/v1/workspaces", json={"name": "test"}).status_code == 401
        assert client.delete("/api/v1/workspaces/team").status_code == 401
        assert client.delete("/api/v1/workspaces/team/channels/10").status_code == 401
        assert client.get("/api/v1/channels/10/messages").status_code == 401
        assert client.get("/api/v1/channels/10/search?q=test").status_code == 401
    assert db.commits == 0


@pytest.mark.asyncio
async def test_deleted_workspace_cannot_be_resolved_or_recreated():
    db = DirectoryDB()
    db.workspace.deleted_at = datetime.now(timezone.utc)
    with pytest.raises(Exception) as error:
        await resolve_workspace(db, "team", lock=True)
    assert error.value.status_code == 410
    assert len(db.records[Workspace]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_target", ["channel", "workspace", "missing_channel"])
async def test_stale_message_send_cannot_recreate_deleted_directories(monkeypatch, delete_target):
    db = DirectoryDB()
    if delete_target == "channel":
        db.channel.deleted_at = datetime.now(timezone.utc)
    elif delete_target == "workspace":
        db.workspace.deleted_at = datetime.now(timezone.utc)
    else:
        db.records[Channel] = []
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(websocket_controller, "async_session_maker", lambda: context)
    assert await websocket_controller.save_message_to_db("team", "10", "2", "stale") is None
    assert len(db.records[Message]) == 2
    assert db.commits == 0


@pytest.mark.asyncio
async def test_stale_websocket_send_to_deleted_channel_is_not_broadcast(monkeypatch):
    from fastapi import WebSocketDisconnect

    db = DirectoryDB()
    db.channel.deleted_at = datetime.now(timezone.utc)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(websocket_controller, "async_session_maker", lambda: context)
    monkeypatch.setattr(websocket_controller, "authenticate_access_token", AsyncMock(return_value=SimpleNamespace(id=2, username="member")))
    monkeypatch.setattr(websocket_controller.manager, "update_presence", AsyncMock())
    broadcast = AsyncMock()
    monkeypatch.setattr(websocket_controller.manager, "broadcast", broadcast)
    socket = MagicMock()
    socket.accept = AsyncMock()
    socket.send_json = AsyncMock()
    socket.receive_json = AsyncMock(side_effect=[
        {"action": "send_message", "channel_id": "10", "content": "stale"}, WebSocketDisconnect(),
    ])
    await websocket_controller.websocket_endpoint(
        socket, token="valid", workspace_id_param="team", user_id_param="1", user_name_param="forged"
    )
    broadcast.assert_not_awaited()
    socket.send_json.assert_awaited_once()
    assert len(db.records[Message]) == 2
    assert db.commits == 0


@pytest.mark.asyncio
async def test_unauthenticated_websocket_is_closed_before_accept(monkeypatch):
    from fastapi import HTTPException

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=DirectoryDB())
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(websocket_controller, "async_session_maker", lambda: context)
    monkeypatch.setattr(websocket_controller, "authenticate_access_token", AsyncMock(side_effect=HTTPException(status_code=401)))
    socket = MagicMock()
    socket.close = AsyncMock()
    socket.accept = AsyncMock()
    await websocket_controller.websocket_endpoint(socket, token="forged", workspace_id_param="team")
    socket.close.assert_awaited_once_with(code=4401)
    socket.accept.assert_not_awaited()
