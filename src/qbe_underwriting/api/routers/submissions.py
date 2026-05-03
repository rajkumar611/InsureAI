from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from qbe_underwriting.platform.database.connection import get_session
from qbe_underwriting.platform.database.models import Submission

router = APIRouter()


class SubmissionCreateRequest(BaseModel):
    submission_ref: str
    class_of_business: str
    jurisdiction: str = "NZ"


class SubmissionResponse(BaseModel):
    submission_id: str
    submission_ref: str
    status: str
    message: str


@router.post(
    "/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_submission(
    body: SubmissionCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SubmissionResponse:
    submission = Submission(
        submission_ref=body.submission_ref,
        class_of_business=body.class_of_business,
        jurisdiction=body.jurisdiction,
        status="RECEIVED",
    )
    session.add(submission)
    await session.commit()
    await session.refresh(submission)

    return SubmissionResponse(
        submission_id=str(submission.id),
        submission_ref=submission.submission_ref,
        status="RECEIVED",
        message="Submission accepted. Processing will begin shortly.",
    )


@router.get("/submissions/{submission_id}", response_model=dict)
async def get_submission(
    submission_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    result = await session.get(Submission, uuid.UUID(submission_id))
    if not result:
        raise HTTPException(status_code=404, detail="Submission not found")

    return {
        "submission_id": str(result.id),
        "submission_ref": result.submission_ref,
        "class_of_business": result.class_of_business,
        "jurisdiction": result.jurisdiction,
        "status": result.status,
        "received_at": result.received_at.isoformat() if result.received_at else None,
    }
