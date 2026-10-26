"""Session identity and administrator flags come from persisted server records."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.controllers.auth_controller import hash_password, router
from app.db.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.auth_service import (
    ACCESS_LIFETIME, REFRESH_LIFETIME, authenticate_access_token,
    get_current_user, issue_session, refresh_session, token_hash,
)


@pytest.fixture(autouse=True)
def init_test_database():
    """These tests use an in-memory session adapter, not a live database."""


class SessionDB:
    def __init__(self):
        self.users = {}
        self.sessions = []
        self.commit_count = 0
        self.refresh_locks = []

    def add(self, value):
        if isinstance(value, AuthSession):
            self.sessions.append(value)
        else:
            value.id = len(self.users) + 1
            value.is_admin = bool(value.is_admin)
            self.users[value.id] = value

    async def flush(self):
        pass

    async def refresh(self, value):
        pass

    async def commit(self):
        self.commit_count += 1

    async def get(self, model, key):
        return self.users.get(key) if model is User else None

    async def scalar(self, statement):
        params = statement.compile().params
        if statement.column_descriptions[0]["entity"] is AuthSession:
            for name in ["access_token_hash", "refresh_token_hash"]:
                if f"{name}_1" in params:
                    if name == "refresh_token_hash":
                        self.refresh_locks.append(statement._for_update_arg is not None)
                    return next((item for item in self.sessions if getattr(item, name) == params[f"{name}_1"]), None)
        for user in self.users.values():
            if user.email == params.get("email_1") or user.username == params.get("username_1"):
                return user
        return None


@pytest.fixture
def db():
    instance = SessionDB()
    instance.add(User(email="member@example.com", username="member", hashed_password=hash_password("secret")))
    return instance


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def database():
        yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as active:
        yield active


@pytest.mark.asyncio
async def test_issued_tokens_are_hashed_and_expire(db):
    before = datetime.now(timezone.utc)
    tokens = await issue_session(db, 1)
    row = db.sessions[0]
    assert row.user_id == 1
    assert row.access_token_hash == token_hash(tokens["access_token"])
    assert row.refresh_token_hash == token_hash(tokens["refresh_token"])
    assert tokens["access_token"] not in vars(row).values()
    assert tokens["refresh_token"] not in vars(row).values()
    assert before + ACCESS_LIFETIME <= row.access_expires_at <= datetime.now(timezone.utc) + ACCESS_LIFETIME
    assert before + REFRESH_LIFETIME <= row.refresh_expires_at <= datetime.now(timezone.utc) + REFRESH_LIFETIME
    assert (await authenticate_access_token(db, tokens["access_token"])).id == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("credentials", [None, HTTPAuthorizationCredentials(scheme="Basic", credentials="anything"),
                                        HTTPAuthorizationCredentials(scheme="Bearer", credentials="forged")])
async def test_missing_or_forged_access_is_unauthorized(db, credentials):
    with pytest.raises(HTTPException) as raised:
        await get_current_user(credentials, db)
    assert raised.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["expired", "revoked", "user-deleted"])
async def test_access_checks_expiration_revocation_and_existing_user(db, state):
    tokens = await issue_session(db, 1)
    if state == "expired":
        db.sessions[0].access_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif state == "revoked":
        db.sessions[0].revoked_at = datetime.now(timezone.utc)
    else:
        db.users.clear()
    with pytest.raises(HTTPException) as raised:
        await authenticate_access_token(db, tokens["access_token"])
    assert raised.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_tokens_and_invalidates_both_old_tokens(db):
    old = await issue_session(db, 1)
    new = await refresh_session(db, old["refresh_token"])
    assert new["refresh_token"] != old["refresh_token"]
    assert new["access_token"] != old["access_token"]
    assert (await authenticate_access_token(db, new["access_token"])).id == 1
    with pytest.raises(HTTPException):
        await refresh_session(db, old["refresh_token"])
    with pytest.raises(HTTPException):
        await authenticate_access_token(db, old["access_token"])
    assert all(db.refresh_locks)
    assert db.commit_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["empty", "forged", "expired", "revoked", "user-deleted"])
async def test_invalid_refresh_is_rejected_without_committing(db, state):
    tokens = await issue_session(db, 1)
    token = tokens["refresh_token"]
    if state == "empty":
        token = ""
    elif state == "forged":
        token = "random-nonempty-token"
    elif state == "expired":
        db.sessions[0].refresh_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif state == "revoked":
        db.sessions[0].revoked_at = datetime.now(timezone.utc)
    else:
        db.users.clear()
    with pytest.raises(HTTPException) as raised:
        await refresh_session(db, token)
    assert raised.value.status_code == 401
    assert db.commit_count == 0


def test_registration_cannot_grant_itself_administration(client, db):
    response = client.post("/api/v1/auth/register", json={
        "email": "new@example.com", "username": "new", "password": "secret", "is_admin": True,
    })
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["is_admin"] is False
    assert data["token_type"] == "bearer"
    assert data["access_token"] and data["refresh_token"]
    assert db.users[2].is_admin is False
    assert db.sessions[-1].user_id == 2


def test_login_returns_server_admin_flag_and_logout_revokes_refresh(client, db):
    db.users[1].is_admin = True
    response = client.post("/api/v1/auth/login", json={"email": "member@example.com", "password": "secret"})
    assert response.status_code == 200
    tokens = response.json()
    assert tokens["user"]["is_admin"] is True
    assert tokens["user"]["id"] == "1"
    assert client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 401


def test_invalid_login_and_logout_do_not_create_sessions(client, db):
    assert client.post("/api/v1/auth/login", json={"email": "member@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "forged"}).status_code == 401
    assert db.sessions == []


@pytest.mark.asyncio
@pytest.mark.parametrize("grant", [True, False])
async def test_operator_cli_changes_only_the_existing_account(monkeypatch, db, grant):
    from scripts import set_admin as command
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    dispose = AsyncMock()
    monkeypatch.setattr(command, "async_session_maker", lambda: context)
    monkeypatch.setattr(command, "engine", SimpleNamespace(dispose=dispose))
    await command.set_admin(" MEMBER@example.com ", grant)
    assert db.users[1].is_admin is grant
    assert db.commit_count == 1
    dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_operator_cli_refuses_unregistered_email(monkeypatch, db):
    from scripts import set_admin as command
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(command, "async_session_maker", lambda: context)
    monkeypatch.setattr(command, "engine", SimpleNamespace(dispose=AsyncMock()))
    with pytest.raises(SystemExit, match="No registered user"):
        await command.set_admin("missing@example.com", True)
    assert db.commit_count == 0
    assert db.users[1].is_admin is False
