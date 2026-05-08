from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.platform.database.connection import get_session

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness — is the process running?"""
    return HealthResponse(status="ok", version="1.0.0")


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_check(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReadinessResponse:
    """Readiness — is the app ready to serve traffic? Checks DB connectivity."""
    try:
        await session.execute(text("SELECT 1"))
        return ReadinessResponse(status="ready", database="ok")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not ready", "database": str(exc)},
        ) from exc
