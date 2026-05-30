"""
Seed test brokers and API keys for Phase 1 testing.
Run: python scripts/seed_brokers.py
"""
import asyncio
import uuid
import hashlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.database.connection import AsyncSessionLocal
from underwriting.database.models import Broker, ApiKey


async def hash_api_key(plain_key: str) -> str:
    """Hash an API key using SHA256."""
    return hashlib.sha256(plain_key.encode()).hexdigest()


async def seed_brokers() -> None:
    """Create test brokers and API keys."""

    test_brokers = [
        {
            "name": "Acme Insurance Brokers",
            "email": "api@acmeinsurance.com",
            "organization": "Acme Inc",
            "api_key": "sk-broker-001-acme-test-key-2026",
        },
        {
            "name": "XYZ Brokers Ltd",
            "email": "contact@xyzbrokers.com",
            "organization": "XYZ Corp",
            "api_key": "sk-broker-002-xyz-test-key-2026",
        },
        {
            "name": "QuickQuote Solutions",
            "email": "api@quickquote.nz",
            "organization": "QuickQuote NZ",
            "api_key": "sk-broker-003-quickquote-test-key-2026",
        },
    ]

    async with AsyncSessionLocal() as session:
        for test_broker in test_brokers:
            # Check if broker already exists
            result = await session.execute(
                select(Broker).where(Broker.email == test_broker["email"])
            )
            existing = result.scalars().first()

            if existing:
                print(f"[OK] Broker '{test_broker['name']}' already exists, skipping")
                continue

            # Create broker
            broker = Broker(
                id=uuid.uuid4(),
                name=test_broker["name"],
                email=test_broker["email"],
                organization=test_broker["organization"],
                status="ACTIVE",
            )
            session.add(broker)
            await session.flush()

            # Create API key
            api_key_hash = await hash_api_key(test_broker["api_key"])
            api_key = ApiKey(
                id=uuid.uuid4(),
                broker_id=broker.id,
                api_key_hash=api_key_hash,
                created_at=datetime.now(),
            )
            session.add(api_key)
            await session.commit()

            print(f"[CREATED] Broker: {test_broker['name']}")
            print(f"  Email: {test_broker['email']}")
            print(f"  API Key (SAVE THIS): {test_broker['api_key']}")
            print(f"  Status: ACTIVE")
            print()


async def main() -> None:
    """Entry point."""
    print("=" * 60)
    print("PHASE 1: Seeding Test Brokers & API Keys")
    print("=" * 60)
    print()

    try:
        await seed_brokers()
        print("[SUCCESS] Seeding complete!")
        print()
        print("Save these API keys for testing:")
        print("  sk-broker-001-acme-test-key-2026")
        print("  sk-broker-002-xyz-test-key-2026")
        print("  sk-broker-003-quickquote-test-key-2026")
    except Exception as e:
        print(f"[ERROR] {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
