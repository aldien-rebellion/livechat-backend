"""Pytest fixtures for backend tests."""
import os
import pytest
from sqlalchemy import text
from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401 - ensure models are registered on Base.metadata

_db_initialized = False


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
async def init_test_database():
    """Ensure all database tables exist before any tests run."""
    global _db_initialized
    if not _db_initialized:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                trigger_sql = """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'messages_search_vector_update') THEN
                        CREATE FUNCTION messages_search_vector_update()
                        RETURNS trigger AS $func$
                        BEGIN
                            NEW.search_vector := to_tsvector('simple', coalesce(NEW.content, ''));
                            RETURN NEW;
                        END;
                        $func$ LANGUAGE plpgsql;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'messages_search_vector_trigger') THEN
                        CREATE TRIGGER messages_search_vector_trigger
                        BEFORE INSERT OR UPDATE OF content
                        ON messages
                        FOR EACH ROW
                        EXECUTE FUNCTION messages_search_vector_update();
                    END IF;
                END $$;
                """
                await conn.execute(text(trigger_sql))
            _db_initialized = True
        except Exception:
            # Gracefully continue if running smoke tests where database is offline
            pass
    yield


@pytest.fixture(autouse=True)
async def cleanup_db_engine():
    """Dispose SQLAlchemy engine connections so asyncpg connections do not leak across event loops."""
    yield
    await engine.dispose()
