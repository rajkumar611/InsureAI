from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qbe_underwriting.pipeline.document_ingestion_agent.agent import run as ingest
from qbe_underwriting.pipeline.human_in_the_loop.schemas import UnderwriterDecision
from qbe_underwriting.platform.database.connection import get_session
from qbe_underwriting.platform.database.models import Submission, UnderwriterQueueItem
from qbe_underwriting.platform.orchestration.workflow import resume_pipeline, run_pipeline

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class PipelineRequest(BaseModel):
    submission_ref: str
    class_of_business: str
    jurisdiction: str = "NZ"
    document_content: str


class QueueDecisionRequest(BaseModel):
    underwriter_id: str
    action: str
    override_risk_score: float | None = None
    override_reason: str | None = None
    conditions: list[str] = []
    exclusions: list[str] = []
    supporting_documents: list[str] = []
    notes: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/submissions/pipeline",
    status_code=status.HTTP_200_OK,
    summary="Ingest document then run the full underwriting pipeline",
)
async def run_full_pipeline(
    body: PipelineRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    # 1. Create and persist the submission row
    submission = Submission(
        submission_ref=body.submission_ref,
        class_of_business=body.class_of_business,
        jurisdiction=body.jurisdiction,
        status="INGESTING",
    )
    session.add(submission)
    await session.flush()
    submission_id = str(submission.id)

    # 2. Document ingestion agent
    try:
        ingestion_result = await ingest(
            submission_id=submission_id,
            class_of_business=body.class_of_business,
            document_content=body.document_content,
            session=session,
        )
        submission.status = "INGESTED"
        submission.extracted_data = ingestion_result.model_dump(mode="json")
        submission.ingestion_confidence = ingestion_result.extraction_confidence
        submission.ingestion_anomalies = ingestion_result.anomalies
        submission.missing_fields = ingestion_result.missing_required_fields
        await session.commit()
    except Exception as exc:
        submission.status = "INGESTION_FAILED"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ingestion failed: {exc}",
        ) from exc

    # 3. Full LangGraph pipeline (may pause at human_review → returns RUNNING)
    try:
        pipeline_state = await run_pipeline(
            submission_id=submission_id,
            submission_data=ingestion_result,
            class_of_business=body.class_of_business,
            jurisdiction=body.jurisdiction,
            thread_id=submission_id,
        )
    except Exception as exc:
        submission.status = "PIPELINE_FAILED"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline failed: {exc}",
        ) from exc

    # 4. Update submission status from pipeline outcome
    wf_status = pipeline_state.get("workflow_status", "UNKNOWN")
    submission.status = wf_status
    await session.commit()

    return {
        "submission_id": submission_id,
        "submission_ref": body.submission_ref,
        "workflow_status": wf_status,
        "ingestion": {
            "extraction_confidence": ingestion_result.extraction_confidence,
            "anomalies": ingestion_result.anomalies,
            "missing_required_fields": ingestion_result.missing_required_fields,
        },
        "claim_profile": pipeline_state.get("claim_profile"),
        "hazard_score": pipeline_state.get("hazard_score"),
        "risk_assessment": pipeline_state.get("risk_assessment"),
        "underwriter_decision": pipeline_state.get("underwriter_decision"),
        "pricing_output": pipeline_state.get("pricing_output"),
        "governance_decision": pipeline_state.get("governance_decision"),
    }


@router.get(
    "/queue",
    summary="List pending underwriter queue items",
)
async def list_queue(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(UnderwriterQueueItem)
        .where(UnderwriterQueueItem.status == "PENDING")
        .order_by(UnderwriterQueueItem.sla_deadline)
    )
    items = rows.scalars().all()
    return [
        {
            "queue_id": str(item.id),
            "submission_id": str(item.submission_id),
            "priority": item.priority,
            "sla_deadline": item.sla_deadline.isoformat(),
            "status": item.status,
            "risk_assessment": item.risk_assessment_snapshot,
            "created_at": item.created_at.isoformat(),
        }
        for item in items
    ]


@router.get(
    "/queue/{queue_id}",
    summary="Get queue item with full submission details",
)
async def get_queue_item(
    queue_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    item = await session.get(UnderwriterQueueItem, uuid.UUID(queue_id))
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    submission = await session.get(Submission, item.submission_id)
    return {
        "queue_id": str(item.id),
        "submission_id": str(item.submission_id),
        "priority": item.priority,
        "sla_deadline": item.sla_deadline.isoformat(),
        "status": item.status,
        "risk_assessment": item.risk_assessment_snapshot,
        "submission": {
            "submission_ref": submission.submission_ref if submission else None,
            "class_of_business": submission.class_of_business if submission else None,
            "jurisdiction": submission.jurisdiction if submission else None,
            "extracted_data": submission.extracted_data if submission else None,
            "ingestion_confidence": submission.ingestion_confidence if submission else None,
            "anomalies": submission.ingestion_anomalies if submission else [],
        } if submission else None,
        "created_at": item.created_at.isoformat(),
    }


@router.post(
    "/queue/{queue_id}/decision",
    summary="Submit underwriter decision and resume the pipeline",
)
async def submit_decision(
    queue_id: str,
    body: QueueDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    item = await session.get(UnderwriterQueueItem, uuid.UUID(queue_id))
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    if item.status != "PENDING":
        raise HTTPException(
            status_code=409, detail=f"Queue item is not PENDING (status={item.status})"
        )

    ra = item.risk_assessment_snapshot or {}
    submission_id = str(item.submission_id)

    uw_decision = UnderwriterDecision(
        submission_id=submission_id,
        underwriter_id=body.underwriter_id,
        action=body.action,
        original_ai_decision=ra.get("risk_decision", "REFER"),
        original_ai_risk_score=ra.get("risk_score", 0.5),
        override_risk_score=body.override_risk_score,
        override_reason=body.override_reason,
        conditions=body.conditions,
        exclusions=body.exclusions,
        supporting_documents=body.supporting_documents,
        notes=body.notes,
    )

    # Resume the LangGraph pipeline (thread_id == submission_id)
    try:
        final_state = await resume_pipeline(
            thread_id=submission_id,
            underwriter_decision=uw_decision,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Pipeline resume failed: {exc}"
        ) from exc

    # Update submission status
    submission = await session.get(Submission, item.submission_id)
    if submission:
        submission.status = final_state.get("workflow_status", "UNKNOWN")
    item.status = "COMPLETED"
    await session.commit()

    return {
        "submission_id": submission_id,
        "queue_id": queue_id,
        "workflow_status": final_state.get("workflow_status"),
        "pricing_output": final_state.get("pricing_output"),
        "governance_decision": final_state.get("governance_decision"),
    }
