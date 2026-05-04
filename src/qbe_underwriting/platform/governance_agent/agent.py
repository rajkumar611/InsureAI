from __future__ import annotations

import json
import logging

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from qbe_underwriting.pipeline.claims_history_agent.schemas import ClaimProfile
from qbe_underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from qbe_underwriting.pipeline.hazard_evaluation_agent.schemas import HazardScore
from qbe_underwriting.pipeline.human_in_the_loop.schemas import UnderwriterDecision
from qbe_underwriting.pipeline.pricing_agent.schemas import PricingOutput
from qbe_underwriting.pipeline.underwriting_risk_agent.schemas import RiskAssessment
from qbe_underwriting.platform.cost_tracking.middleware import record_llm_cost
from qbe_underwriting.platform.governance_agent.schemas import GovernanceDecision
from qbe_underwriting.platform.llm.client import anthropic_client, model_for
from qbe_underwriting.platform.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "governance_agent"
COMPLIANCE_RULES_VERSION = "QBE-COMPLIANCE-NZ-AU-2024-v1"
MAX_RETRIES = 2


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


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

    system_prompt = prompt_template.render(
        submission_id=submission_id,
        submission_data=json.dumps(submission_data.model_dump(mode="json"), indent=2),
        claim_profile=json.dumps(claim_profile.model_dump(mode="json"), indent=2),
        hazard_score=json.dumps(hazard_score.model_dump(mode="json"), indent=2),
        risk_assessment=json.dumps(risk_assessment.model_dump(mode="json"), indent=2),
        underwriter_decision=json.dumps(underwriter_decision.model_dump(mode="json"), indent=2),
        pricing_output=json.dumps(pricing_output.model_dump(mode="json"), indent=2),
        compliance_rules_version=COMPLIANCE_RULES_VERSION,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "governance_agent: attempt %d/%d  submission=%s",
            attempt, MAX_RETRIES, submission_id,
        )

        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=4096,
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

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(_extract_first_json_object(raw))
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
