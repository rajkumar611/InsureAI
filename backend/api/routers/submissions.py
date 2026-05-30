from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline_agents.document_ingestion_agent.agent import run as ingest
from database.connection import get_session
from database.models import Submission
from engine.orchestration import workflow

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
    import hashlib
    import json

    try:
        uuid.UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission_id — must be a UUID")

    if workflow.graph is None:
        raise HTTPException(
            status_code=503,
            detail="Workflow not initialized",
        )

    config = {"configurable": {"thread_id": submission_id}}
    entries = []
    prev_hash = None

    async for state in workflow.graph.aget_state_history(config):
        values = state.values or {}

        # Infer step from which values are populated (LangGraph doesn't set metadata step)
        step = "initialization"
        if values.get("governance_decision"):
            step = "governance"
        elif values.get("pricing_output"):
            step = "pricing"
        elif values.get("underwriter_decision"):
            step = "human_review"
        elif values.get("risk_assessment"):
            step = "underwriting_risk"
        elif values.get("hazard_score") or values.get("claim_profile"):
            if values.get("hazard_score") and values.get("claim_profile"):
                step = "parallel_analysis"
            elif values.get("hazard_score"):
                step = "hazard_evaluation"
            else:
                step = "claims_history"
        elif values.get("submission_data"):
            step = "document_ingestion"

        # Extract decision and confidence based on step
        decision_value = ""
        confidence_score = None
        parsed_output = None

        if step == "document_ingestion" and values.get("submission_data"):
            decision_value = "EXTRACTED"
            parsed_output = values.get("submission_data")
        elif step == "claims_history" and values.get("claim_profile"):
            decision_value = "ANALYZED"
            parsed_output = values.get("claim_profile")
        elif step == "hazard_evaluation" and values.get("hazard_score"):
            hazard = values.get("hazard_score")
            decision_value = "SCORED"
            confidence_score = hazard.get("confidence", 0) if isinstance(hazard, dict) else None
            parsed_output = hazard
        elif step == "parallel_analysis":
            decision_value = "PARALLEL_ANALYSIS_COMPLETE"
            parsed_output = {
                "claims": values.get("claim_profile"),
                "hazard": values.get("hazard_score"),
            }
        elif step == "underwriting_risk" and values.get("risk_assessment"):
            risk = values.get("risk_assessment")
            if isinstance(risk, dict):
                decision_value = risk.get("risk_decision", "PENDING")
                confidence_score = risk.get("risk_score")
            parsed_output = risk
        elif step == "pricing" and values.get("pricing_output"):
            decision_value = "PRICED"
            parsed_output = values.get("pricing_output")
        elif step == "governance" and values.get("governance_decision"):
            gov = values.get("governance_decision")
            decision_value = gov.get("verdict", "PENDING") if isinstance(gov, dict) else "PENDING"
            parsed_output = gov
        elif step == "human_review" and values.get("underwriter_decision"):
            uw_dec = values.get("underwriter_decision")
            if isinstance(uw_dec, dict):
                decision_value = uw_dec.get("action", "PENDING")
            parsed_output = uw_dec

        # Create entry content for hashing
        entry_content = {
            "step": step,
            "decision": decision_value,
            "timestamp": state.created_at,
            "workflow_status": values.get("workflow_status"),
        }
        entry_str = json.dumps(entry_content, sort_keys=True, default=str)
        entry_hash = hashlib.sha256(entry_str.encode()).hexdigest()[:16]

        entry = {
            "event_type": step.replace("_", " ").title(),
            "agent_name": step.replace("_", " ").title(),
            "decision_value": decision_value,
            "timestamp": state.created_at,
            "confidence_score": confidence_score,
            "entry_hash": entry_hash,
            "previous_hash": prev_hash,
            "parsed_output": parsed_output,
        }

        # Add underwriter info if it's a human review
        if step == "human_review" and isinstance(values.get("underwriter_decision"), dict):
            uw_dec = values.get("underwriter_decision")
            entry["underwriter_id"] = uw_dec.get("underwriter_id")
            entry["override_reason"] = uw_dec.get("override_reason")
            entry["decision_rationale"] = uw_dec.get("notes")

        entries.append(entry)
        prev_hash = entry_hash

    entries.reverse()
    return entries
