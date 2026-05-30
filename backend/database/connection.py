"""Database connection and session management."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from pydantic_settings import BaseSettings
import os

class DatabaseSettings(BaseSettings):
    """Database configuration from environment."""
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://qbe:localdev@localhost:5432/aus_underwriting"
    )

    class Config:
        env_file = ".env"

_settings = DatabaseSettings()

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
