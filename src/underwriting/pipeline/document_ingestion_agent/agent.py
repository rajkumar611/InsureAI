from __future__ import annotations

import json
import logging

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from underwriting.platform.audit.writer import record_agent_decision
from underwriting.platform.cost_tracking.middleware import record_llm_cost
from underwriting.platform.llm.client import anthropic_client, model_for
from underwriting.platform.llm.parsing import strip_markdown_fences
from underwriting.platform.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "document_ingestion_agent"


MAX_RETRIES = 2


async def run(
    *,
    submission_id: str,
    class_of_business: str,
    document_content: str,
    session: AsyncSession,
) -> SubmissionData:
    """
    Extract structured submission data from raw broker document text.

    Sends the versioned system prompt as the Anthropic `system` parameter.
    User turn is a simple trigger so Claude knows to respond.
    Validates response against SubmissionData schema — retries once on failure.
    Records real token cost to the cost_ledger table.
    """
    prompt_template = PromptRegistry.load(AGENT_NAME)
    model = model_for(AGENT_NAME)

    system_prompt = prompt_template.render(
        submission_id=submission_id,
        class_of_business=class_of_business,
        document_content=document_content,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "document_ingestion_agent: attempt %d/%d  submission=%s",
            attempt, MAX_RETRIES, submission_id,
        )

        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=0,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "Extract the structured data from the broker document provided.",
                }
            ],
        )

        await record_llm_cost(
            session=session,
            response=response,
            agent_name=AGENT_NAME,
            prompt_version=str(prompt_template.version),
            class_of_business=class_of_business,
            feature_tag="extraction",
        )

        if not response.content:
            raise ValueError("LLM returned empty response")
        raw_text = strip_markdown_fences(response.content[0].text)
        logger.debug("document_ingestion_agent: raw response: %s", raw_text[:200])

        try:
            submission_data = SubmissionData.model_validate(json.loads(raw_text))
            logger.info(
                "document_ingestion_agent: extraction success  "
                "confidence=%s  missing=%s  anomalies=%d",
                submission_data.extraction_confidence,
                submission_data.missing_required_fields,
                len(submission_data.anomalies),
            )
            _conf_map = {"high": 0.90, "medium": 0.70, "low": 0.50}
            await record_agent_decision(
                session=session,
                submission_id=submission_id,
                agent_name=AGENT_NAME,
                event_type="DOCUMENT_INGESTED",
                decision_value=submission_data.extraction_confidence,
                confidence_score=_conf_map.get(submission_data.extraction_confidence or ""),
                parsed_output=submission_data.model_dump(mode="json"),
                prompt_version=str(prompt_template.version),
            )
            return submission_data

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "document_ingestion_agent: attempt %d failed — %s: %s",
                attempt, type(exc).__name__, exc,
            )
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"document_ingestion_agent failed after {MAX_RETRIES} attempts "
                    f"for submission {submission_id}.\n"
                    f"Last error: {exc}\n"
                    f"Last response: {raw_text[:500]}"
                ) from exc
