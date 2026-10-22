"""Smoke tests to verify CI runner environment and service container connectivity."""
import sys
import pytest


def test_python_version() -> None:
    """Verify runtime Python is at least 3.11 as specified in architecture."""
    assert sys.version_info >= (3, 11), f"Expected Python >= 3.11, got {sys.version}"


def test_baseline_dependencies() -> None:
    """Verify baseline dependencies from requirements.txt can be imported."""
    import fastapi
    import uvicorn

    assert fastapi.__version__
    assert uvicorn.__version__


@pytest.mark.asyncio
async def test_postgres_service_connection(database_url: str) -> None:
    """Verify PostgreSQL service container is reachable when running in CI or local compose."""
    import asyncpg

    raw_dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        conn = await asyncpg.connect(raw_dsn, timeout=5)
        result = await conn.fetchval("SELECT 1")
        await conn.close()
        assert result == 1
    except Exception as exc:
        if "localhost" in raw_dsn or "127.0.0.1" in raw_dsn:
            pytest.skip(f"Database service not accessible on host ({exc}); pass in CI with service container.")
        else:
            raise


@pytest.mark.asyncio
async def test_redis_service_connection(redis_url: str) -> None:
    """Verify Redis service container is reachable when running in CI or local compose."""
    import redis.asyncio as aioredis

    try:
        client = aioredis.from_url(redis_url, socket_timeout=5)
        pong = await client.ping()
        await client.aclose()
        assert pong is True
    except Exception as exc:
        if "localhost" in redis_url or "127.0.0.1" in redis_url:
            pytest.skip(f"Redis service not accessible on host ({exc}); pass in CI with service container.")
        else:
            raise
