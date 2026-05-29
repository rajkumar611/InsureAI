from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.pipeline_agents.document_ingestion_agent.agent import run as ingest
from underwriting.database.connection import get_session
from underwriting.database.models import Submission
from underwriting.platform.orchestration.workflow import graph

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
    "/submissions/{ref}",
    response_model=dict,
    summary="Get submission by policy number or submission ID",
)
async def get_submission(
    ref: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    result = None

    # Try lookup by policy number / submission_ref first
    row = await session.execute(
        select(Submission).where(Submission.submission_ref == ref)
    )
    result = row.scalars().first()

    # Fall back to UUID lookup
    if not result:
        try:
            result = await session.get(Submission, uuid.UUID(ref))
        except (ValueError, AttributeError):
            pass

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


@router.get(
    "/audit/{submission_id}",
    summary="Get audit trail for a submission",
)
async def get_audit_trail(submission_id: str) -> list[dict]:
    try:
        uuid.UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission_id — must be a UUID")

    if graph is None:
        raise HTTPException(
            status_code=503,
            detail="Workflow not initialized",
        )

    config = {"configurable": {"thread_id": submission_id}}
    steps = []

    async for state in graph.aget_state_history(config):
        writes = state.metadata.get("writes") or {}
        steps.append({
            "step": state.metadata.get("step"),
            "node": list(writes.keys()),
            "workflow_status": state.values.get("workflow_status"),
            "next": list(state.next),
            "state_snapshot": state.values,
            "checkpoint_id": state.config["configurable"].get("checkpoint_id"),
            "created_at": state.created_at.isoformat() if state.created_at else None,
        })

    steps.reverse()
    return steps
