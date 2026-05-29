from __future__ import annotations

import uuid

from anthropic.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.platform.cost_tracking.pricing import calculate_cost
from underwriting.platform.database.models import CostEntry


async def record_llm_cost(
    *,
    session: AsyncSession,
    response: Message,
    agent_name: str,
    submission_id: uuid.UUID | None = None,
    policy_id: str | None = None,
    prompt_version: str | None = None,
    feature_tag: str | None = None,
    class_of_business: str | None = None,
    jurisdiction: str | None = None,
) -> CostEntry:
    """
    Called immediately after every Anthropic API response.
    Reads real token counts from the response, calculates cost, persists to DB.
    """
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    model_id = response.model

    cost_usd = calculate_cost(model_id, input_tokens, output_tokens)

    entry = CostEntry(
        submission_id=submission_id,
        policy_id=policy_id,
        agent_name=agent_name,
        prompt_version=prompt_version,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        feature_tag=feature_tag,
        class_of_business=class_of_business,
        jurisdiction=jurisdiction,
    )
    session.add(entry)
    await session.flush()
    return entry
