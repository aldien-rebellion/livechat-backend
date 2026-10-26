import hashlib
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import bearer, get_access_session, issue_session, refresh_session, unauthorized

router = APIRouter(prefix="/auth", tags=["Auth"])


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}:{key.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt, key_hex = hashed_password.split(":")
        new_key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return secrets.compare_digest(new_key.hex(), key_hex)
    except Exception:
        return False


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str
    is_admin: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    username_clean = payload.username.strip()

    # Check if user already exists
    existing = await db.scalar(
        select(User).where((User.email == email_clean) | (User.username == username_clean))
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email or username is already registered.",
        )

    # Create new user
    new_user = User(
        email=email_clean,
        username=username_clean,
        hashed_password=hash_password(payload.password),
    )
    db.add(new_user)
    await db.flush()
    tokens = await issue_session(db, new_user.id)
    await db.commit()
    await db.refresh(new_user)

    return {
        **tokens,
        "user": {
            "id": str(new_user.id),
            "email": new_user.email,
            "username": new_user.username,
            "full_name": payload.full_name or new_user.username,
            "is_admin": bool(getattr(new_user, "is_admin", False)),
        },
    }


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    email_clean = payload.email.strip().lower()
    user = await db.scalar(select(User).where(User.email == email_clean))

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )

    tokens = await issue_session(db, user.id)
    await db.commit()

    return {
        **tokens,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "full_name": user.username,
            "is_admin": bool(getattr(user, "is_admin", False)),
        },
    }


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await refresh_session(db, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    session = await get_access_session(db, credentials.credentials)
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
