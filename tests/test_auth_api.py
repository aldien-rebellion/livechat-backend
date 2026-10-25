import secrets
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.controllers.auth_controller import hash_password, verify_password


def test_hash_and_verify_password():
    pwd = "secure_test_password_123!"
    hashed = hash_password(pwd)
    assert ":" in hashed
    assert verify_password(pwd, hashed) is True
    assert verify_password("wrong_password", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(pwd, "invalid_format_hash") is False


@pytest.mark.asyncio
async def test_auth_full_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rand_suffix = secrets.token_hex(4)
        email = f"testuser_{rand_suffix}@example.com"
        username = f"user_{rand_suffix}"
        password = "Password123!"
        full_name = "Test User Full"

        # 1. Register
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "username": username,
                "password": password,
                "full_name": full_name,
            },
        )
        assert reg_res.status_code == 201, reg_res.text
        reg_data = reg_res.json()
        assert "access_token" in reg_data
        assert "refresh_token" in reg_data
        assert reg_data["token_type"] == "bearer"
        assert reg_data["user"]["email"] == email
        assert reg_data["user"]["username"] == username
        assert reg_data["user"]["full_name"] == full_name

        # 2. Duplicate registration should return 409 Conflict
        dup_res = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "username": username,
                "password": password,
            },
        )
        assert dup_res.status_code == 409

        # 3. Login with correct credentials
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": password,
            },
        )
        assert login_res.status_code == 200
        login_data = login_res.json()
        assert "access_token" in login_data
        assert "refresh_token" in login_data
        assert login_data["user"]["email"] == email

        # 4. Login with wrong password should return 401
        wrong_pwd_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": email,
                "password": "wrong_password!",
            },
        )
        assert wrong_pwd_res.status_code == 401

        # 5. Login with non-existent email should return 401
        unknown_user_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent_email_404@example.com",
                "password": password,
            },
        )
        assert unknown_user_res.status_code == 401

        # 6. Refresh token with valid refresh_token
        refresh_res = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": login_data["refresh_token"],
            },
        )
        assert refresh_res.status_code == 200
        ref_data = refresh_res.json()
        assert "access_token" in ref_data
        assert ref_data["token_type"] == "bearer"

        # 7. Refresh token with empty string should return 401
        empty_ref_res = await client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": "",
            },
        )
        assert empty_ref_res.status_code == 401
