from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.pipeline.claims_history_agent.schemas import ClaimProfile
from underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from underwriting.pipeline.hazard_evaluation_agent.schemas import HazardScore
from underwriting.pipeline.human_in_the_loop.schemas import UnderwriterDecision
from underwriting.pipeline.pricing_agent.schemas import PricingOutput
from underwriting.pipeline.underwriting_risk_agent.schemas import RiskAssessment
from underwriting.platform.audit.writer import record_agent_decision
from underwriting.platform.cost_tracking.middleware import record_llm_cost
from underwriting.platform.database.models import Regulation
from underwriting.platform.governance_agent.schemas import GovernanceDecision
from underwriting.platform.llm.client import anthropic_client, model_for
from underwriting.platform.llm.parsing import extract_first_json_object
from underwriting.platform.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "governance_agent"
COMPLIANCE_RULES_VERSION = "AI-UW-COMPLIANCE-NZ-AU-2024-v1"
MAX_RETRIES = 2


async def _fetch_regulations(
    session: AsyncSession,
    jurisdiction: str,
    class_of_business: str,
) -> str:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(Regulation).where(
            Regulation.jurisdiction == jurisdiction,
            Regulation.class_of_business == class_of_business,
            Regulation.effective_date <= now,
            (Regulation.expiry_date == None) | (Regulation.expiry_date > now),  # noqa: E711
        )
    )
    rules = result.scalars().all()
    if not rules:
        return "No active regulations found for this jurisdiction and class of business."
    lines = []
    for r in rules:
        lines.append(f"[{r.rule_code} v{r.version}] {r.rule_description}")
        lines.append(f"  Regulator: {r.regulator}  |  Data: {json.dumps(r.rule_data)}")
    return "\n".join(lines)


async def run(
    *,
    submission_id: str,
    submission_data: SubmissionData,
    claim_profile: ClaimProfile,
    hazard_score: HazardScore,
    risk_assessment: RiskAssessment,
    underwriter_decision: UnderwriterDecision,
    pricing_output: PricingOutput,
    class_of_business: str,
    jurisdiction: str,
    session: AsyncSession,
) -> GovernanceDecision:
    """
    Final gatekeeper before policy issuance.

    Validates the entire workflow chain for consistency, completeness,
    compliance, and fraud signals using Claude Sonnet.
    Returns APPROVED, REJECTED, or REFER_TO_SENIOR_UNDERWRITER.
    """
    prompt_template = PromptRegistry.load(AGENT_NAME)
    model = model_for(AGENT_NAME)

    active_regulations = await _fetch_regulations(session, jurisdiction, class_of_business)

    system_prompt = prompt_template.render(
        submission_id=submission_id,
        submission_data=json.dumps(submission_data.model_dump(mode="json"), indent=2),
        claim_profile=json.dumps(claim_profile.model_dump(mode="json"), indent=2),
        hazard_score=json.dumps(hazard_score.model_dump(mode="json"), indent=2),
        risk_assessment=json.dumps(risk_assessment.model_dump(mode="json"), indent=2),
        underwriter_decision=json.dumps(underwriter_decision.model_dump(mode="json"), indent=2),
        pricing_output=json.dumps(pricing_output.model_dump(mode="json"), indent=2),
        compliance_rules_version=COMPLIANCE_RULES_VERSION,
        active_regulations=active_regulations,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "governance_agent: attempt %d/%d  submission=%s",
            attempt, MAX_RETRIES, submission_id,
        )

        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "Validate the full workflow chain and produce the GovernanceDecision JSON.",
                }
            ],
        )

        await record_llm_cost(
            session=session,
            response=response,
            agent_name=AGENT_NAME,
            prompt_version=str(prompt_template.version),
            class_of_business=class_of_business,
            jurisdiction=jurisdiction,
            feature_tag="governance",
        )

        if not response.content:
            raise ValueError("LLM returned empty response")
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(extract_first_json_object(raw))
            # Always inject the canonical version
            data["compliance_rules_version"] = COMPLIANCE_RULES_VERSION
            # Drop unknown top-level fields
            allowed = GovernanceDecision.model_fields.keys()
            data = {k: v for k, v in data.items() if k in allowed}
            decision = GovernanceDecision.model_validate(data)
            logger.info(
                "governance_agent: outcome=%s  passed=%d  failed=%d",
                decision.governance_outcome,
                len(decision.checks_passed),
                len(decision.checks_failed),
            )
            await record_agent_decision(
                session=session,
                submission_id=submission_id,
                agent_name=AGENT_NAME,
                event_type="GOVERNANCE_DECISION",
                decision_value=decision.governance_outcome,
                parsed_output=decision.model_dump(mode="json"),
                prompt_version=COMPLIANCE_RULES_VERSION,
            )
            return decision

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "governance_agent: attempt %d failed — %s: %s",
                attempt, type(exc).__name__, exc,
            )
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"governance_agent failed after {MAX_RETRIES} attempts "
                    f"for submission {submission_id}.\nLast error: {exc}\nResponse: {raw[:400]}"
                ) from exc
