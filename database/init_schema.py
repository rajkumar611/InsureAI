"""Initialize database schema if tables don't exist."""
import asyncio
import logging
from pathlib import Path
import asyncpg

logger = logging.getLogger(__name__)

async def check_and_init_schema() -> None:
    """Check if database schema exists. If not, create it from schema.sql."""
    try:
        from underwriting.database.connection import get_db_url

        db_url = get_db_url()
        dsn = db_url.replace("postgresql+asyncpg://", "").replace("postgresql://", "")

        # Parse connection string
        parts = dsn.split("@")
        auth = parts[0].split(":")
        user, password = auth[0], auth[1]

        host_db = parts[1].split("/")
        host = host_db[0].split(":")[0]
        port = int(host_db[0].split(":")[1]) if ":" in host_db[0] else 5432
        database = host_db[1]

        # Connect and check if tables exist
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )

        try:
            result = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='submissions')"
            )

            if not result:
                logger.info("Database schema not found. Initializing from database_schema.sql...")
                schema_file = Path(__file__).parent / "database_schema.sql"

                if not schema_file.exists():
                    logger.error(f"database_schema.sql not found at {schema_file}")
                    raise FileNotFoundError(f"database_schema.sql not found at {schema_file}")

                with open(schema_file, "r") as f:
                    schema_sql = f.read()

                # Execute schema
                await conn.execute(schema_sql)
                logger.info("Database schema initialized successfully")
            else:
                logger.info("Database schema already exists")
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Error initializing schema: {e}")
        raise
