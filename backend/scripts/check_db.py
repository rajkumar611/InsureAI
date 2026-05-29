import asyncio
from underwriting.platform.database.connection import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as s:
        for table in ["customers", "claims", "claims_embeddings"]:
            r = await s.execute(text(f"SELECT COUNT(*) FROM {table}"))
            print(f"{table}: {r.scalar()} rows")

asyncio.run(main())
