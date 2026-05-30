"""
Database health check — verify connectivity and row counts in key tables.

Usage:
    uv run python database/health_check_db.py
"""
import asyncio

from sqlalchemy import text

from database.connection import AsyncSessionLocal


async def main():
    """Check database health by querying row counts."""
    async with AsyncSessionLocal() as s:
        tables = ["customers", "claims", "claims_embeddings", "brokers", "regulations"]
        for table in tables:
            r = await s.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = r.scalar()
            print(f"  {table}: {count} rows")


if __name__ == "__main__":
    print("=" * 50)
    print("DATABASE HEALTH CHECK")
    print("=" * 50)
    asyncio.run(main())
    print("\n[SUCCESS] Database is healthy!")
