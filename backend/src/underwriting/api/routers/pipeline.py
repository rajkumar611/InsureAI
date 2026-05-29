from __future__ import annotations

import os
import time
import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.pipeline_agents.document_ingestion_agent.agent import run as ingest
from underwriting.pipeline_agents.document_ingestion_agent.schemas import SubmissionData
from underwriting.pipeline_agents.human_in_the_loop.schemas import UnderwriterDecision
from underwriting.database.connection import get_session
from underwriting.database.models import CostEntry, Submission, UnderwriterQueueItem
from underwriting.platform.orchestration.workflow import resume_pipeline, run_pipeline
from underwriting.platform.progress_tracker import clear as clear_progress, get_step, set_step

router = APIRouter()

# Daily spend cap — override via DAILY_SPEND_CAP_USD env var (default $10)
_DAILY_SPEND_CAP_USD = Decimal(os.getenv("DAILY_SPEND_CAP_USD", "10.00"))


async def _check_daily_spend_cap(session: AsyncSession) -> None:
    """Raise HTTP 429 if today's LLM spend has reached the configured cap."""
    result = await session.execute(
        select(func.coalesce(func.sum(CostEntry.cost_usd), 0))
        .where(func.date(CostEntry.timestamp) == func.current_date())
    )
    today_spend = Decimal(str(result.scalar()))
    if today_spend >= _DAILY_SPEND_CAP_USD:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily LLM spend cap of ${_DAILY_SPEND_CAP_USD} USD reached "
                f"(today: ${today_spend:.4f} USD). "
                "Pipeline submissions are paused until tomorrow or the cap is raised."
            ),
        )


# ── Request / Response models ─────────────────────────────────────────────────

_COB_SUFFIX = {
    "property": "PPY",
    "liability": "LBY",
    "marine": "CGO",
    "motor": "MOT",
    "specialty": "SPC",
}


def _generate_policy_number(class_of_business: str) -> str:
    suffix = _COB_SUFFIX.get(class_of_business.lower(), "GEN")
    seq = f"{int(time.time() * 1000) % 10000000:07d}"
    return f"P{seq}{suffix}"


class PipelineRequest(BaseModel):
    submission_id: uuid.UUID | None = None
    submission_ref: str | None = None
    class_of_business: Literal["property", "liability", "motor", "marine", "professional_indemnity"]
    jurisdiction: Literal["NZ", "AU"] = "NZ"
    document_content: str = Field(..., min_length=50, max_length=500_000)


class QueueDecisionRequest(BaseModel):
    underwriter_id: str = Field(..., min_length=1)
    action: Literal["ACCEPT", "DECLINE", "REFER"]
    override_risk_score: float | None = Field(None, ge=0.0, le=1.0)
    override_reason: str | None = None
    conditions: list[str] = []
    exclusions: list[str] = []
    supporting_documents: list[str] = []
    notes: str = Field(default="", max_length=5000)


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
    await _check_daily_spend_cap(session)

    # 1. Create and persist the submission row with a temporary internal ref
    temp_ref = f"TEMP-{uuid.uuid4().hex[:12].upper()}"
    sub_kwargs: dict = dict(
        submission_ref=body.submission_ref or temp_ref,
        class_of_business=body.class_of_business,
        jurisdiction=body.jurisdiction,
        status="INGESTING",
    )
    if body.submission_id:
        sub_kwargs["id"] = body.submission_id
    submission = Submission(**sub_kwargs)
    session.add(submission)
    await session.flush()
    submission_id = str(submission.id)

    set_step(submission_id, "document_ingestion")

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
        await session.rollback()
        submission.status = "INGESTION_FAILED"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ingestion failed: {exc}",
        ) from exc

    # 3. Early-exit — deterministic Python checks, no LLM involved.
    #    Any failure stops the pipeline immediately after Document Ingestion.

    # 3a. Mandatory field check — inspect extracted values directly.
    #     If the LLM couldn't find a value in the document it returns null (None).
    _MANDATORY: dict[str, object] = {
        "insured_name":        ingestion_result.insured_name,
        "risk_address":        ingestion_result.risk_address,
        "sum_insured":         ingestion_result.sum_insured,
        "sum_insured_currency": ingestion_result.sum_insured_currency,
        "coverage_type":       ingestion_result.coverage_type,
        "policy_period_start": ingestion_result.policy_period_start,
        "policy_period_end":   ingestion_result.policy_period_end,
    }
    _missing_critical = [f for f, v in _MANDATORY.items() if not v]

    # 3b. Prompt injection — check anomaly text flagged by the ingestion agent.
    _injection_keywords = ("injection", "ignore previous", "disregard your", "unrestricted mode")
    _injection_snippets = [
        a for a in ingestion_result.anomalies
        if any(kw in a.lower() for kw in _injection_keywords)
    ]

    if _missing_critical or _injection_snippets:
        if _injection_snippets:
            decline_reason = "PROMPT_INJECTION"
            decline_message = (
                "Prompt injection content was detected in this document. "
                "Please remove such text and resubmit a clean broker document."
            )
        else:
            fields = ", ".join(_missing_critical)
            decline_reason = "MISSING_MANDATORY_FIELDS"
            decline_message = (
                f"The following mandatory fields are missing from the document: {fields}. "
                "Please resubmit with all required fields completed."
            )

        policy_number = _generate_policy_number(body.class_of_business)
        submission.submission_ref = policy_number
        submission.status = "DECLINED"
        await session.commit()
        clear_progress(submission_id)

        return {
            "submission_id": submission_id,
            "submission_ref": policy_number,
            "workflow_status": "DECLINED",
            "decline_reason": decline_reason,
            "decline_message": decline_message,
            "missing_critical_fields": _missing_critical,
            "injection_snippets": _injection_snippets,
            "claim_profile": None,
            "hazard_score": None,
            "risk_assessment": None,
            "underwriter_decision": None,
            "pricing_output": None,
            "governance_decision": None,
        }

    # 4. Full LangGraph pipeline (may pause at human_review → returns AWAITING_HUMAN)
    try:
        pipeline_state = await run_pipeline(
            submission_id=submission_id,
            submission_data=ingestion_result,
            class_of_business=body.class_of_business,
            jurisdiction=body.jurisdiction,
            thread_id=submission_id,
        )
    except Exception as exc:
        await session.rollback()
        submission.status = "PIPELINE_FAILED"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline failed: {exc}",
        ) from exc

    # 5. Assign policy number and update submission status
    clear_progress(submission_id)
    wf_status = pipeline_state.get("workflow_status", "UNKNOWN")
    policy_number = _generate_policy_number(body.class_of_business)
    submission.submission_ref = policy_number
    submission.status = wf_status
    await session.commit()

    return {
        "submission_id": submission_id,
        "submission_ref": policy_number,
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
    "/submissions/{submission_id}/progress",
    summary="Poll current pipeline step for a running submission",
)
async def get_pipeline_progress(submission_id: str) -> dict[str, str | None]:
    return {"step": get_step(submission_id)}


_QUEUE_PAGE_SIZE = 10


@router.get(
    "/queue",
    summary="List pending underwriter queue items",
)
async def list_queue(
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
) -> dict[str, Any]:
    offset = (page - 1) * _QUEUE_PAGE_SIZE

    total_result = await session.execute(
        select(UnderwriterQueueItem.id)
        .where(UnderwriterQueueItem.status == "PENDING")
    )
    total = len(total_result.all())

    rows = await session.execute(
        select(UnderwriterQueueItem, Submission)
        .join(Submission, UnderwriterQueueItem.submission_id == Submission.id, isouter=True)
        .where(UnderwriterQueueItem.status == "PENDING")
        .order_by(UnderwriterQueueItem.sla_deadline)
        .limit(_QUEUE_PAGE_SIZE)
        .offset(offset)
    )
    pairs = rows.all()

    return {
        "page": page,
        "page_size": _QUEUE_PAGE_SIZE,
        "total": total,
        "total_pages": max(1, -(-total // _QUEUE_PAGE_SIZE)),  # ceiling division
        "items": [
            {
                "queue_id": str(item.id),
                "submission_id": str(item.submission_id),
                "submission_ref": sub.submission_ref if sub else None,
                "priority": item.priority,
                "sla_deadline": item.sla_deadline.isoformat(),
                "status": item.status,
                "risk_assessment": item.risk_assessment_snapshot,
                "created_at": item.created_at.isoformat(),
                "class_of_business": sub.class_of_business if sub else None,
                "jurisdiction": sub.jurisdiction if sub else None,
                "extracted_data": sub.extracted_data if sub else {},
                "ingestion_confidence": sub.ingestion_confidence if sub else None,
                "anomalies": sub.ingestion_anomalies if sub else [],
            }
            for item, sub in pairs
        ],
    }


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
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Pipeline checkpoint is incomplete for submission {submission_id} "
                f"(missing state key: {exc}). This submission was likely created during "
                "a prior API error. Please resubmit the document to create a fresh pipeline."
            ),
        ) from exc
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
