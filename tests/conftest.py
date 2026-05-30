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

TEST_DATABASE_URL = "postgresql+asyncpg://qbe:localdev@localhost:5432/aus_underwriting_test"


@pytest_asyncio.fixture(scope="session")
async def setup_test_db():
    """Create and tear down the test database schema. Lazy — only runs when requested."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Load schema from SQL file
    schema_file = Path(__file__).parent.parent / "database" / "database_schema.sql"
    if schema_file.exists():
        with open(schema_file, "r") as f:
            schema_sql = f.read()

        async with engine.begin() as conn:
            await conn.exec_driver_sql(schema_sql)

    yield engine

    # Drop all tables (simple cleanup)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(setup_test_db) -> AsyncSession:
    SessionLocal = async_sessionmaker(
        bind=setup_test_db, class_=AsyncSession, expire_on_commit=False
    )
    async with SessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    from httpx import ASGITransport, AsyncClient
    from main import app
    from database.connection import get_session

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
