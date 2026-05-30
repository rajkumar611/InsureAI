from __future__ import annotations

import json
import logging
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline_agents.claims_history_agent.schemas import ClaimProfile
from pipeline_agents.document_ingestion_agent.schemas import SubmissionData
from pipeline_agents.hazard_evaluation_agent.schemas import HazardScore
from pipeline_agents.underwriting_risk_agent.schemas import RiskAssessment
from engine.cost_tracking.middleware import record_llm_cost
from engine.llm.client import anthropic_client, model_for
from engine.llm.parsing import extract_first_json_object
from engine.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "underwriting_risk_agent"
GUIDELINES_VERSION = "AI-UW-NZ-AU-2024-v1"
MAX_RETRIES = 2

_FIFTY_MILLION = Decimal("50000000")

# ── Deterministic scoring formulas ────────────────────────────────────────────
# LLM decides ACCEPT/DECLINE/REFER and writes rationale.
# These formulas produce stable numeric outputs from the same structured inputs,
# ensuring identical documents always yield identical scores regardless of
# submission_id or minor LLM float variation.

_HAZARD_BASE_SCORE: dict[str, float] = {
    "LOW": 0.20, "MEDIUM": 0.45, "HIGH": 0.70, "EXTREME": 0.90,
}
_FREQ_TREND_ADJ: dict[str, float] = {
    "INCREASING": 0.05, "STABLE": 0.00, "DECREASING": -0.03, "INSUFFICIENT_DATA": 0.02,
}


def _deterministic_risk_score(hazard_score: HazardScore, claim_profile: ClaimProfile) -> float:
    base = _HAZARD_BASE_SCORE.get(hazard_score.overall_hazard_level, 0.45)
    claims_adj = min(claim_profile.total_claims_3yr * 0.05, 0.20)
    large_loss_adj = 0.05 if claim_profile.largest_single_loss > Decimal("200000") else 0.0
    trend_adj = _FREQ_TREND_ADJ.get(claim_profile.claim_frequency_trend, 0.0)
    return round(min(0.99, max(0.01, base + claims_adj + large_loss_adj + trend_adj)), 2)


def _compute_signal_conflict(hazard_score: HazardScore, claim_profile: ClaimProfile) -> bool:
    """Deterministic signal conflict: fires when hazard and claims data point in opposite directions."""
    high_hazard = hazard_score.overall_hazard_level in ("HIGH", "EXTREME")
    low_hazard = hazard_score.overall_hazard_level in ("LOW", "NEGLIGIBLE")
    risky_claims = (
        claim_profile.total_claims_3yr >= 3
        or claim_profile.largest_single_loss > Decimal("500000")
        or bool({"HIGH_FREQUENCY", "FRAUD_SUSPICION", "REPEAT_FLOOD", "REPEAT_FIRE"} & set(claim_profile.risk_flags))
    )
    clean_claims = (
        claim_profile.total_claims_3yr == 0
        and claim_profile.claim_frequency_trend in ("DECREASING", "INSUFFICIENT_DATA")
        and not claim_profile.risk_flags
    )
    return (low_hazard and risky_claims) or (high_hazard and clean_claims)


def _deterministic_confidence(
    hazard_score: HazardScore,
    claim_profile: ClaimProfile,
    submission_data: SubmissionData,
    signal_conflict: bool,
) -> float:
    conf = 0.92
    if claim_profile.data_quality == "LOW":
        conf -= 0.15
    elif claim_profile.data_quality == "MEDIUM":
        conf -= 0.05
    conf -= len(hazard_score.data_gaps) * 0.04
    if signal_conflict:
        conf -= 0.10
    if submission_data.extraction_confidence == "medium":
        conf -= 0.03
    elif submission_data.extraction_confidence == "low":
        conf -= 0.10
    return round(max(0.50, min(0.98, conf)), 2)


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

    # data_quality == LOW is passed to the LLM risk agent — it has full context
    # (submission declared claims, hazard score) to make a nuanced judgment.
    # Hard pre-screen only for fraud and extreme hazard combinations.

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
        assessment = _build_pre_screen_assessment(
            submission_id=submission_id,
            decision=decision,
            rule=rule,
            submission_data=submission_data,
            claim_profile=claim_profile,
            hazard_score=hazard_score,
        )
        return assessment

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
            temperature=0,
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

        if not response.content:
            raise ValueError("LLM returned empty response")
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(extract_first_json_object(raw))
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

            # Override LLM-generated floats with deterministic formulas so that
            # identical input documents always produce identical numeric outputs.
            assessment.signal_conflict = _compute_signal_conflict(hazard_score, claim_profile)
            assessment.risk_score = _deterministic_risk_score(hazard_score, claim_profile)
            assessment.confidence_score = _deterministic_confidence(
                hazard_score, claim_profile, submission_data, assessment.signal_conflict
            )

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
