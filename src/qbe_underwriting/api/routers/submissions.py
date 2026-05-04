from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from qbe_underwriting.pipeline.document_ingestion_agent.agent import run as ingest
from qbe_underwriting.platform.database.connection import get_session
from qbe_underwriting.platform.database.models import Submission

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class SubmissionCreateRequest(BaseModel):
    submission_ref: str
    class_of_business: str
    jurisdiction: str = "NZ"


class IngestRequest(BaseModel):
    submission_ref: str
    class_of_business: str
    jurisdiction: str = "NZ"
    document_content: str


class SubmissionResponse(BaseModel):
    submission_id: str
    submission_ref: str
    status: str
    message: str


class IngestResponse(BaseModel):
    submission_id: str
    submission_ref: str
    status: str
    extraction_confidence: str
    anomalies: list[str]
    missing_required_fields: list[str]
    extracted_data: dict


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register a submission (no processing)",
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
        message="Submission registered. Call /ingest to process the document.",
    )


@router.post(
    "/submissions/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit a document and run the ingestion agent",
)
async def ingest_submission(
    body: IngestRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IngestResponse:
    # Create submission row with INGESTING status
    submission = Submission(
        submission_ref=body.submission_ref,
        class_of_business=body.class_of_business,
        jurisdiction=body.jurisdiction,
        status="INGESTING",
    )
    session.add(submission)
    await session.flush()
    submission_id = str(submission.id)

    try:
        result = await ingest(
            submission_id=submission_id,
            class_of_business=body.class_of_business,
            document_content=body.document_content,
            session=session,
        )

        # Persist extracted data back to the submission row
        submission.status = "INGESTED"
        submission.extracted_data = result.model_dump(mode="json")
        submission.ingestion_confidence = result.extraction_confidence
        submission.ingestion_anomalies = result.anomalies
        submission.missing_fields = result.missing_required_fields

        await session.commit()

        return IngestResponse(
            submission_id=submission_id,
            submission_ref=body.submission_ref,
            status="INGESTED",
            extraction_confidence=result.extraction_confidence,
            anomalies=result.anomalies,
            missing_required_fields=result.missing_required_fields,
            extracted_data=result.model_dump(mode="json"),
        )

    except Exception as exc:
        submission.status = "INGESTION_FAILED"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ingestion failed: {exc}",
        ) from exc


@router.get(
    "/submissions/{submission_id}",
    response_model=dict,
    summary="Get submission status and extracted data",
)
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
        "extraction_confidence": result.ingestion_confidence,
        "anomalies": result.ingestion_anomalies or [],
        "missing_required_fields": result.missing_fields or [],
        "extracted_data": result.extracted_data,
        "received_at": result.received_at.isoformat() if result.received_at else None,
    }
