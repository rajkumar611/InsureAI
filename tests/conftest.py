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
TEST_API_KEY = "test-api-key-12345"


@pytest_asyncio.fixture(scope="session")
async def setup_test_db():
    """Create test database once per session."""
    from database.models import Base

    # Create admin connection to postgres database
    postgres_url = "postgresql+asyncpg://qbe:localdev@localhost:5432/postgres"
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

    # Create test broker and API key once
    from database.models import Broker, ApiKey
    from uuid import uuid4
    import hashlib

    SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        broker = Broker(
            id=uuid4(),
            name="test-broker",
            email="test@broker.com",
            organization="Test Org",
            status="ACTIVE",
        )
        session.add(broker)
        await session.flush()

        key_hash = hashlib.sha256(TEST_API_KEY.encode()).hexdigest()
        api_key = ApiKey(
            id=uuid4(),
            broker_id=broker.id,
            api_key_hash=key_hash,
        )
        session.add(api_key)
        await session.commit()

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
async def db_session_with_broker(setup_test_db):
    """Session with test broker and API key (created at session scope)."""
    SessionLocal = async_sessionmaker(
        bind=setup_test_db, class_=AsyncSession, expire_on_commit=False
    )

    session = SessionLocal()
    try:
        yield session, TEST_API_KEY
    finally:
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def db_session(db_session_with_broker):
    session, _ = db_session_with_broker
    return session


@pytest_asyncio.fixture
async def client(db_session_with_broker):
    from httpx import ASGITransport, AsyncClient
    from main import app
    from database.connection import get_session

    db_session, test_api_key = db_session_with_broker

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    # Create client with test API key header
    headers = {"X-API-Key": test_api_key}
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=headers
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
