"""Database-backed opaque sessions. Only token hashes are persisted."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.auth_session import AuthSession
from app.models.user import User


bearer = HTTPBearer(auto_error=False)
ACCESS_LIFETIME = timedelta(hours=1)
REFRESH_LIFETIME = timedelta(days=7)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Please sign in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def expired(value: datetime, now: datetime) -> bool:
    # PostgreSQL returns aware values; tolerate naive UTC in test/session adapters.
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value) <= now


def rotate_tokens(session: AuthSession, now: datetime) -> dict:
    access = secrets.token_urlsafe(32)
    refresh = secrets.token_urlsafe(48)
    session.access_token_hash = token_hash(access)
    session.refresh_token_hash = token_hash(refresh)
    session.access_expires_at = now + ACCESS_LIFETIME
    session.refresh_expires_at = now + REFRESH_LIFETIME
    session.revoked_at = None
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


async def issue_session(db: AsyncSession, user_id: int) -> dict:
    session = AuthSession(user_id=user_id)
    tokens = rotate_tokens(session, datetime.now(timezone.utc))
    db.add(session)
    return tokens


async def get_access_session(db: AsyncSession, token: str) -> AuthSession:
    if not token:
        raise unauthorized()
    session = await db.scalar(select(AuthSession).where(AuthSession.access_token_hash == token_hash(token)))
    if session is None or session.revoked_at is not None or expired(session.access_expires_at, datetime.now(timezone.utc)):
        raise unauthorized()
    return session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    return await authenticate_access_token(db, credentials.credentials)


async def authenticate_access_token(db: AsyncSession, token: str) -> User:
    session = await get_access_session(db, token)
    user = await db.get(User, session.user_id)
    if user is None:
        raise unauthorized()
    return user


async def refresh_session(db: AsyncSession, token: str) -> dict:
    if not token:
        raise unauthorized()
    session = await db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == token_hash(token)).with_for_update()
    )
    now = datetime.now(timezone.utc)
    if session is None or session.revoked_at is not None or expired(session.refresh_expires_at, now):
        raise unauthorized()
    if await db.get(User, session.user_id) is None:
        raise unauthorized()
    tokens = rotate_tokens(session, now)
    await db.commit()
    return tokens
