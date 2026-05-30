"""
API Key authentication middleware for broker submissions.

All /api/v1/* endpoints require X-API-Key header.
API keys are hashed with SHA256 before comparison.
"""
import hashlib
import logging
from datetime import datetime

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import AsyncSessionLocal
from database.models import Broker, ApiKey

logger = logging.getLogger(__name__)


async def hash_api_key(plain_key: str) -> str:
    """Hash an API key using SHA256."""
    return hashlib.sha256(plain_key.encode()).hexdigest()


async def authenticate_api_key(request: Request, call_next) -> Response:
    """
    Middleware: Check API key in X-API-Key header.

    If valid:
      - Attach broker info to request.state
      - Update last_used_at timestamp
      - Allow request to continue

    If invalid/missing:
      - Return 401 Unauthorized
    """

    # Skip authentication for health checks
    if request.url.path.startswith("/health"):
        return await call_next(request)

    # Skip for non-API endpoints (e.g., docs)
    if not request.url.path.startswith("/api/v1"):
        return await call_next(request)

    # Extract API key from header
    api_key = request.headers.get("X-API-Key")

    if not api_key:
        return Response(
            content='{"detail":"Missing X-API-Key header"}',
            status_code=401,
            media_type="application/json",
        )

    try:
        # Hash the provided key
        api_key_hash = await hash_api_key(api_key)

        # Query database for this key
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ApiKey, Broker)
                .join(Broker, ApiKey.broker_id == Broker.id)
                .where(ApiKey.api_key_hash == api_key_hash)
            )
            row = result.first()

        if not row:
            return Response(
                content='{"detail":"Invalid API key"}',
                status_code=401,
                media_type="application/json",
            )

        api_key_obj, broker = row

        # Check if broker is active
        if broker.status != "ACTIVE":
            return Response(
                content='{"detail":"Broker account is inactive"}',
                status_code=403,
                media_type="application/json",
            )

        # Attach broker info to request state
        request.state.broker_id = str(broker.id)
        request.state.broker_name = broker.name
        request.state.broker_email = broker.email

        # Update last_used_at (non-blocking, fire and forget)
        try:
            async with AsyncSessionLocal() as session:
                api_key_obj_to_update = await session.get(ApiKey, api_key_obj.id)
                if api_key_obj_to_update:
                    api_key_obj_to_update.last_used_at = datetime.now()
                    await session.commit()
        except (SQLAlchemyError, Exception) as exc:
            logger.warning("Failed to update API key last_used_at: %s", exc)

        # Allow request to continue
        response = await call_next(request)

        # Optionally add broker info to response headers
        response.headers["X-Broker-ID"] = request.state.broker_id
        response.headers["X-Broker-Name"] = request.state.broker_name

        return response

    except Exception as exc:
        logger.error(
            "Authentication error for request %s: %s",
            request.url.path,
            exc,
            exc_info=True,
        )
        return Response(
            content='{"detail":"Authentication error"}',
            status_code=500,
            media_type="application/json",
        )
