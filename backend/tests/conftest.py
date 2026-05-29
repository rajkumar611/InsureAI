from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "postgresql+asyncpg://qbe:localdev@localhost:5432/aus_underwriting_test"


@pytest_asyncio.fixture(scope="session")
async def setup_test_db():
    """Create and tear down the test database schema. Lazy — only runs when requested."""
    from underwriting.platform.database.models import Base

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
    from backend.main import app
    from underwriting.platform.database.connection import get_session

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
