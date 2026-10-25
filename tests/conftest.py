"""Pytest fixtures for backend tests."""
import os
import pytest
from app.db.session import engine


@pytest.fixture(scope="session")
def database_url() -> str:
    """Return database URL from environment or default local URL."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/livechat_db",
    )


@pytest.fixture(scope="session")
def redis_url() -> str:
    """Return Redis URL from environment or default local URL."""
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(autouse=True)
async def cleanup_db_engine():
    """Dispose SQLAlchemy engine connections so asyncpg connections do not leak across event loops."""
    yield
    await engine.dispose()
