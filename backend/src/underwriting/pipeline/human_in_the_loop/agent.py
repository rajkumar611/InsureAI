from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.pipeline.human_in_the_loop.schemas import UnderwriterDecision
from underwriting.pipeline.underwriting_risk_agent.schemas import RiskAssessment
from underwriting.platform.database.models import UnderwriterQueueItem

logger = logging.getLogger(__name__)

# SLA: 5 business days for standard cases, 2 for HIGH/EXTREME risk
_SLA_STANDARD_DAYS = 5
_SLA_HIGH_RISK_DAYS = 2


def _sla_deadline(risk_assessment: RiskAssessment) -> datetime:
    days = _SLA_HIGH_RISK_DAYS if risk_assessment.risk_score >= 0.75 else _SLA_STANDARD_DAYS
    return datetime.now(timezone.utc) + timedelta(days=days)


def _priority(risk_assessment: RiskAssessment) -> str:
    if risk_assessment.risk_score >= 0.80:
        return "HIGH"
    if risk_assessment.risk_score >= 0.60:
        return "STANDARD"
    return "LOW"


async def enqueue(
    *,
    submission_id: str,
    risk_assessment: RiskAssessment,
    session: AsyncSession,
    workflow_id: str | None = None,
    pipeline_state: dict | None = None,
) -> UnderwriterQueueItem:
    """
    Add a REFER case to the underwriter review queue.
    Called by the orchestration layer when risk_decision == REFER.
    Returns the queue item so the workflow can store its ID.
    pipeline_state stores the full workflow state so resume works after server restart.
    """
    wf_id = uuid.UUID(workflow_id) if workflow_id else uuid.uuid4()

    item = UnderwriterQueueItem(
        workflow_id=wf_id,
        submission_id=uuid.UUID(submission_id),
        priority=_priority(risk_assessment),
        sla_deadline=_sla_deadline(risk_assessment),
        status="PENDING",
        risk_assessment_snapshot=risk_assessment.model_dump(mode="json"),
        pipeline_state_snapshot=pipeline_state,
    )
    session.add(item)
    await session.flush()

    logger.info(
        "human_in_the_loop: queued  submission=%s  priority=%s  sla=%s  queue_id=%s",
        submission_id,
        item.priority,
        item.sla_deadline.date(),
        item.id,
    )
    return item


async def record_decision(
    *,
    queue_item: UnderwriterQueueItem,
    decision: UnderwriterDecision,
    session: AsyncSession,
) -> UnderwriterQueueItem:
    """
    Persist the underwriter's decision back to the queue row.
    Called when the underwriter submits their review via the UI/API.
    """
    queue_item.status = "COMPLETED"
    queue_item.decision = decision.model_dump(mode="json")
    queue_item.completed_at = datetime.now(timezone.utc)
    await session.flush()

    logger.info(
        "human_in_the_loop: decision recorded  action=%s  underwriter=%s  submission=%s",
        decision.action,
        decision.underwriter_id,
        decision.submission_id,
    )
    return queue_item


def simulate_approval(
    *,
    submission_id: str,
    risk_assessment: RiskAssessment,
    underwriter_id: str = "UW-DEV-001",
) -> UnderwriterDecision:
    """
    Simulate an underwriter APPROVE_WITH_CONDITIONS decision for dev/testing.
    Not called in production — the real decision comes from the UI.
    """
    conditions: list[str] = []
    exclusions: list[str] = []

    # Mirror the AI's primary risk factors as conditions
    for factor in risk_assessment.primary_risk_factors[:2]:
        conditions.append(f"Risk acknowledged: {factor}")

    if risk_assessment.signal_conflict:
        conditions.append(
            "Underwriter has reviewed and resolved signal conflict noted by AI"
        )

    if risk_assessment.risk_score >= 0.65:
        conditions.append("Annual risk survey required within 90 days of policy inception")
        conditions.append("Insured to provide engineering certificate for structural risk")

    return UnderwriterDecision(
        submission_id=submission_id,
        underwriter_id=underwriter_id,
        action="APPROVE_WITH_CONDITIONS",
        original_ai_decision=risk_assessment.risk_decision,
        original_ai_risk_score=risk_assessment.risk_score,
        override_risk_score=round(risk_assessment.risk_score * 0.90, 2),
        override_reason="Human review completed — risk score adjusted 10% on confirmation of property details",
        conditions=conditions,
        exclusions=exclusions,
        notes="Simulated approval for development pipeline testing.",
    )
