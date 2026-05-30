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
    # First, ensure test database exists by connecting to postgres and creating it
    postgres_url = "postgresql+asyncpg://qbe:localdev@localhost:5432/postgres"
    admin_engine = create_async_engine(postgres_url, echo=False, isolation_level="AUTOCOMMIT")

    try:
        async with admin_engine.begin() as conn:
            await conn.exec_driver_sql(
                "CREATE DATABASE aus_underwriting_test;"
            )
    except Exception:
        # Database might already exist, that's fine
        pass
    finally:
        await admin_engine.dispose()

    # Now connect to test database and create schema from ORM models
    from database.models import Base
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Create tables from ORM models (synchronous)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables (simple cleanup)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    except Exception:
        # Schema might be partially dropped, that's OK
        pass
    finally:
        await engine.dispose()

        # Clean up test database
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
    """Session with test broker and API key."""
    from database.models import Broker, ApiKey
    from uuid import uuid4
    import hashlib

    SessionLocal = async_sessionmaker(
        bind=setup_test_db, class_=AsyncSession, expire_on_commit=False
    )

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

        test_api_key = "test-api-key-12345"
        key_hash = hashlib.sha256(test_api_key.encode()).hexdigest()

        api_key = ApiKey(
            id=uuid4(),
            broker_id=broker.id,
            api_key_hash=key_hash,
        )
        session.add(api_key)
        await session.commit()

        yield session, test_api_key
        await session.rollback()


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
