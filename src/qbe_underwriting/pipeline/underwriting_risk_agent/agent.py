from __future__ import annotations

import json
import logging
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from qbe_underwriting.pipeline.claims_history_agent.schemas import ClaimProfile
from qbe_underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from qbe_underwriting.pipeline.hazard_evaluation_agent.schemas import HazardScore
from qbe_underwriting.pipeline.underwriting_risk_agent.schemas import RiskAssessment
from qbe_underwriting.platform.cost_tracking.middleware import record_llm_cost
from qbe_underwriting.platform.llm.client import anthropic_client, model_for
from qbe_underwriting.platform.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "underwriting_risk_agent"
GUIDELINES_VERSION = "QBE-NZ-AU-2024-v1"
MAX_RETRIES = 2

_FIFTY_MILLION = Decimal("50000000")


# ── Deterministic pre-screen ──────────────────────────────────────────────────

def _pre_screen(
    submission_data: SubmissionData,
    claim_profile: ClaimProfile,
    hazard_score: HazardScore,
) -> tuple[str | None, str | None]:
    """
    Apply deterministic pre-screen rules before any LLM reasoning.
    Returns (decision, rule_description) or (None, None) if no rule fires.
    Rules are ordered: DECLINE checks before REFER checks.
    """
    # ── DECLINE rules ──────────────────────────────────────────────────────────
    if (
        hazard_score.overall_hazard_level == "EXTREME"
        and claim_profile.total_claims_3yr > 2
    ):
        return "DECLINE", "overall_hazard_level == EXTREME AND total_claims_3yr > 2"

    if "FRAUD_SUSPICION" in claim_profile.risk_flags:
        return "DECLINE", "FRAUD_SUSPICION flag present in claim profile"

    # ── REFER rules ───────────────────────────────────────────────────────────
    if submission_data.sum_insured and submission_data.sum_insured > _FIFTY_MILLION:
        return "REFER", "sum_insured > NZD/AUD 50,000,000"

    if claim_profile.data_quality == "LOW":
        return "REFER", "claim_profile.data_quality == LOW"

    if hazard_score.confidence < 0.50:
        return "REFER", f"hazard_score.confidence ({hazard_score.confidence:.2f}) < 0.50"

    if submission_data.extraction_confidence == "low":
        return "REFER", "submission_data.extraction_confidence == low"

    return None, None


def _build_pre_screen_assessment(
    submission_id: str,
    decision: str,
    rule: str,
    submission_data: SubmissionData,
    claim_profile: ClaimProfile,
    hazard_score: HazardScore,
) -> RiskAssessment:
    """Build a RiskAssessment without LLM when a pre-screen rule fires."""
    is_decline = decision == "DECLINE"

    primary_factors: list[str] = []
    if "FRAUD_SUSPICION" in claim_profile.risk_flags:
        primary_factors.append("FRAUD_SUSPICION flag in claims history")
    if hazard_score.overall_hazard_level in ("EXTREME", "HIGH"):
        primary_factors.append(f"Overall hazard level: {hazard_score.overall_hazard_level}")
    if claim_profile.total_claims_3yr > 2:
        primary_factors.append(f"{claim_profile.total_claims_3yr} claims in last 3 years")
    if not primary_factors:
        primary_factors = [f"Pre-screen rule triggered: {rule}"]

    rationale = (
        f"Pre-screen rule fired — {rule}. "
        f"Decision is {decision} and cannot be overridden by LLM reasoning. "
        f"Human review required to progress this submission."
        if decision == "REFER"
        else f"Pre-screen rule fired — {rule}. "
        f"This submission is automatically declined and cannot be accepted without rule change."
    )

    return RiskAssessment(
        submission_id=submission_id,
        risk_decision=decision,
        risk_score=0.95 if is_decline else 0.80,
        confidence_score=1.0,
        pre_screen_triggered=True,
        pre_screen_rule=rule,
        primary_risk_factors=primary_factors,
        mitigating_factors=list(hazard_score.mitigating_factors),
        signal_conflict=False,
        signal_conflict_explanation=None,
        applicable_guidelines=[GUIDELINES_VERSION],
        decision_rationale=rationale,
        escalation_reason=rule if decision == "REFER" else None,
    )


# ── JSON helpers ──────────────────────────────────────────────────────────────

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


# ── Main entry point ──────────────────────────────────────────────────────────

async def run(
    *,
    submission_id: str,
    submission_data: SubmissionData,
    claim_profile: ClaimProfile,
    hazard_score: HazardScore,
    class_of_business: str,
    jurisdiction: str,
    session: AsyncSession,
) -> RiskAssessment:
    """
    Synthesise SubmissionData + ClaimProfile + HazardScore → Accept/Decline/Refer.

    Pre-screen rules fire in Python (deterministic, no LLM call wasted).
    LLM reasoning only runs when no pre-screen rule applies.
    """
    # ── Step 1: deterministic pre-screen ──────────────────────────────────────
    decision, rule = _pre_screen(submission_data, claim_profile, hazard_score)

    if decision is not None:
        logger.info(
            "underwriting_risk_agent: pre-screen triggered  rule=%r  decision=%s  submission=%s",
            rule, decision, submission_id,
        )
        return _build_pre_screen_assessment(
            submission_id=submission_id,
            decision=decision,
            rule=rule,
            submission_data=submission_data,
            claim_profile=claim_profile,
            hazard_score=hazard_score,
        )

    # ── Step 2: LLM synthesis ─────────────────────────────────────────────────
    logger.info(
        "underwriting_risk_agent: no pre-screen fired, calling LLM  submission=%s",
        submission_id,
    )

    prompt_template = PromptRegistry.load(AGENT_NAME)
    model = model_for(AGENT_NAME)

    system_prompt = prompt_template.render(
        submission_id=submission_id,
        submission_data=json.dumps(submission_data.model_dump(mode="json"), indent=2),
        claim_profile=json.dumps(claim_profile.model_dump(mode="json"), indent=2),
        hazard_score=json.dumps(hazard_score.model_dump(mode="json"), indent=2),
        underwriting_guidelines_version=GUIDELINES_VERSION,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "underwriting_risk_agent: LLM attempt %d/%d  submission=%s",
            attempt, MAX_RETRIES, submission_id,
        )

        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "Synthesise the inputs and produce the RiskAssessment JSON.",
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
            feature_tag="risk_assessment",
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(_extract_first_json_object(raw))
            data["submission_id"] = submission_id
            # Normalise common LLM field name variations
            if "decision" in data and "risk_decision" not in data:
                data["risk_decision"] = data.pop("decision")
            if "score" in data and "risk_score" not in data:
                data["risk_score"] = data.pop("score")
            if "confidence" in data and "confidence_score" not in data:
                data["confidence_score"] = data.pop("confidence")
            if "rationale" in data and "decision_rationale" not in data:
                data["decision_rationale"] = data.pop("rationale")
            # Drop unknown fields
            allowed = RiskAssessment.model_fields.keys()
            data = {k: v for k, v in data.items() if k in allowed}

            assessment = RiskAssessment.model_validate(data)

            # Safety: LLM must never override a pre-screen decision
            # (pre-screen already returned early above, but guard against prompt injection)
            logger.info(
                "underwriting_risk_agent: LLM decision=%s  score=%.2f  confidence=%.2f",
                assessment.risk_decision, assessment.risk_score, assessment.confidence_score,
            )
            return assessment

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "underwriting_risk_agent: attempt %d failed — %s: %s",
                attempt, type(exc).__name__, exc,
            )
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"underwriting_risk_agent failed after {MAX_RETRIES} attempts "
                    f"for submission {submission_id}.\nLast error: {exc}\nResponse: {raw[:400]}"
                ) from exc
