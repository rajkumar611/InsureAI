from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.platform.database.models import AuditEntry


def _compute_hash(entry_id: int, submission_id: str, agent_name: str,
                  event_type: str, decision_value: str | None,
                  previous_hash: str | None) -> str:
    payload = {
        "id": entry_id,
        "submission_id": submission_id,
        "agent_name": agent_name,
        "event_type": event_type,
        "decision_value": decision_value,
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()


async def record_agent_decision(
    *,
    session: AsyncSession,
    submission_id: str | uuid.UUID,
    agent_name: str,
    event_type: str,
    decision_value: str | None = None,
    decision_rationale: str | None = None,
    confidence_score: float | None = None,
    parsed_output: dict | None = None,
    prompt_version: str | None = None,
    underwriter_id: str | None = None,
    override_reason: str | None = None,
    processing_time_ms: int | None = None,
) -> AuditEntry:
    """
    Append one immutable row to audit_trail for an agent decision.
    Hash-chains each entry to the previous one for the same submission.
    Must be called within an open session — caller is responsible for commit.
    """
    sid = uuid.UUID(str(submission_id))

    prev_result = await session.execute(
        select(AuditEntry.entry_hash)
        .where(AuditEntry.submission_id == sid)
        .order_by(AuditEntry.id.desc())
        .limit(1)
    )
    previous_hash = prev_result.scalar()

    entry = AuditEntry(
        submission_id=sid,
        agent_name=agent_name,
        event_type=event_type,
        decision_value=decision_value,
        decision_rationale=decision_rationale,
        confidence_score=confidence_score,
        parsed_output=parsed_output,
        prompt_version=prompt_version,
        underwriter_id=underwriter_id,
        override_reason=override_reason,
        processing_time_ms=processing_time_ms,
        previous_hash=previous_hash,
    )
    session.add(entry)
    await session.flush()

    entry.entry_hash = _compute_hash(
        entry_id=entry.id,
        submission_id=str(sid),
        agent_name=agent_name,
        event_type=event_type,
        decision_value=decision_value,
        previous_hash=previous_hash,
    )
    await session.flush()
    return entry
