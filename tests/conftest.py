from __future__ import annotations

import sys
from pathlib import Path

# Add backend and root to sys.path (prioritize over stdlib) for 'engine' module conflict
backend_path = Path(__file__).parent.parent / "backend"
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))
sys.path.insert(0, str(root_path))

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "postgresql+asyncpg://dbinsureai:125QueenStreet@localhost:5432/aus_underwriting_test"


@pytest_asyncio.fixture(scope="session")
async def setup_test_db():
    """Create test database once per session."""
    from database.models import Base

    # Create admin connection to postgres database
    postgres_url = "postgresql+asyncpg://dbinsureai:125QueenStreet@localhost:5432/postgres"
    admin_engine = create_async_engine(postgres_url, echo=False, isolation_level="AUTOCOMMIT")

    # Drop test database if it exists (clean slate)
    try:
        async with admin_engine.begin() as conn:
            await conn.exec_driver_sql("DROP DATABASE IF EXISTS aus_underwriting_test;")
    except Exception:
        pass

    # Create fresh test database
    try:
        async with admin_engine.begin() as conn:
            await conn.exec_driver_sql("CREATE DATABASE aus_underwriting_test;")
    except Exception as e:
        pass
    finally:
        await admin_engine.dispose()

    # Create async engine for test database
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Create all tables from ORM models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup: drop database after all tests
    await engine.dispose()
    admin_engine = create_async_engine(postgres_url, echo=False, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.begin() as conn:
            await conn.exec_driver_sql("DROP DATABASE IF EXISTS aus_underwriting_test;")
    except Exception:
        pass
    finally:
        await admin_engine.dispose()


@pytest_asyncio.fixture
async def db_session(setup_test_db):
    """Database session for tests."""
    SessionLocal = async_sessionmaker(
        bind=setup_test_db, class_=AsyncSession, expire_on_commit=False
    )

    session = SessionLocal()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def client(db_session):
    from httpx import ASGITransport, AsyncClient
    from main import app
    from database.connection import get_session

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    # Create public API client (no authentication required)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
