"""Database connection and session management."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
import os

class DatabaseSettings(BaseSettings):
    """Database configuration from environment."""
    model_config = ConfigDict(extra="ignore")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

_settings = DatabaseSettings()

if not _settings.DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable must be set")

def get_db_url() -> str:
    """Get database URL."""
    return _settings.DATABASE_URL

# Create async engine
engine = create_async_engine(_settings.DATABASE_URL, echo=False, future=True)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    """Dependency for getting database session."""
    async with AsyncSessionLocal() as session:
        yield session
