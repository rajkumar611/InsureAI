from __future__ import annotations

import json
import logging
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from qbe_underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from qbe_underwriting.pipeline.human_in_the_loop.schemas import UnderwriterDecision
from qbe_underwriting.pipeline.pricing_agent.schemas import PricingOutput
from qbe_underwriting.pipeline.underwriting_risk_agent.schemas import RiskAssessment
from qbe_underwriting.platform.cost_tracking.middleware import record_llm_cost
from qbe_underwriting.platform.llm.client import anthropic_client, model_for
from qbe_underwriting.platform.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "pricing_agent"
ACTUARIAL_TABLE_VERSION = "QBE-NZ-AU-PROP-2024-v1"
MAX_RETRIES = 2

# ── Simulated market rate data ─────────────────────────────────────────────────
# In production: pull from actuarial rate engine or rating API.

_MARKET_RATES: dict[str, dict[str, dict]] = {
    "property": {
        "NZ": {
            "base_rate_per_mille": 1.20,        # 0.12% of sum insured p.a.
            "min_base_rate_per_mille": 0.60,    # floor for any risk
            "seismic_high_loading_pct": 25,     # +25% for HIGH seismic zone
            "seismic_extreme_loading_pct": 50,  # +50% for EXTREME
            "flood_high_loading_pct": 20,
            "flood_extreme_loading_pct": 45,
            "fire_high_loading_pct": 15,
            "claims_loading_per_claim_3yr_pct": 5,  # +5% per claim in 3yr
            "large_loss_loading_pct": 10,
            "sprinkler_discount_pct": 10,
            "monitored_alarm_discount_pct": 5,
            "no_claims_5yr_discount_pct": 10,
            "post_2000_build_discount_pct": 5,
            "technical_minimum_nzd": 750,
            "standard_excess_pct_sum_insured": 0.2,   # 0.2% of SI
            "currency": "NZD",
        },
        "AU": {
            "base_rate_per_mille": 1.35,
            "min_base_rate_per_mille": 0.70,
            "seismic_high_loading_pct": 10,
            "seismic_extreme_loading_pct": 25,
            "flood_high_loading_pct": 25,
            "flood_extreme_loading_pct": 55,
            "fire_high_loading_pct": 30,       # bushfire exposure AU
            "claims_loading_per_claim_3yr_pct": 5,
            "large_loss_loading_pct": 10,
            "sprinkler_discount_pct": 10,
            "monitored_alarm_discount_pct": 5,
            "no_claims_5yr_discount_pct": 10,
            "post_2000_build_discount_pct": 5,
            "technical_minimum_aud": 900,
            "standard_excess_pct_sum_insured": 0.2,
            "currency": "AUD",
        },
    },
    "liability": {
        "NZ": {"base_rate_per_mille": 0.80, "currency": "NZD"},
        "AU": {"base_rate_per_mille": 0.95, "currency": "AUD"},
    },
    "marine": {
        "NZ": {"base_rate_per_mille": 1.50, "currency": "NZD"},
        "AU": {"base_rate_per_mille": 1.65, "currency": "AUD"},
    },
}

_DEFAULT_RATES = {"base_rate_per_mille": 1.20, "currency": "NZD"}


def _market_rates(class_of_business: str, jurisdiction: str) -> dict:
    cob = class_of_business.lower()
    return (
        _MARKET_RATES.get(cob, {}).get(jurisdiction, _DEFAULT_RATES)
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
    risk_assessment: RiskAssessment,
    underwriter_decision: UnderwriterDecision,
    class_of_business: str,
    jurisdiction: str,
    session: AsyncSession,
) -> PricingOutput:
    """
    Calculate premium using Claude Haiku.

    Runs only after human sign-off (UnderwriterDecision.action in APPROVE*).
    Prices against the effective_risk_score (override if set, else original).
    """
    if underwriter_decision.action not in (
        "APPROVE", "APPROVE_WITH_CONDITIONS", "OVERRIDE"
    ):
        raise ValueError(
            f"pricing_agent: cannot price — underwriter action is "
            f"'{underwriter_decision.action}', expected APPROVE / APPROVE_WITH_CONDITIONS / OVERRIDE"
        )

    rates = _market_rates(class_of_business, jurisdiction)

    prompt_template = PromptRegistry.load(AGENT_NAME)
    model = model_for(AGENT_NAME)

    system_prompt = prompt_template.render(
        submission_id=submission_id,
        submission_data=json.dumps(submission_data.model_dump(mode="json"), indent=2),
        risk_assessment=json.dumps(risk_assessment.model_dump(mode="json"), indent=2),
        underwriter_decision=json.dumps(underwriter_decision.model_dump(mode="json"), indent=2),
        market_rate_data=json.dumps(rates, indent=2),
        actuarial_table_version=ACTUARIAL_TABLE_VERSION,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "pricing_agent: attempt %d/%d  submission=%s",
            attempt, MAX_RETRIES, submission_id,
        )

        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "Calculate the premium and produce the PricingOutput JSON.",
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
            feature_tag="pricing",
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(_extract_first_json_object(raw))
            data["submission_id"] = submission_id
            data["actuarial_table_version"] = ACTUARIAL_TABLE_VERSION
            # Drop unknown fields
            allowed = PricingOutput.model_fields.keys()
            data = {k: v for k, v in data.items() if k in allowed}
            output = PricingOutput.model_validate(data)
            logger.info(
                "pricing_agent: success  final_premium=%s %s  method=%s",
                output.final_premium, output.premium_currency, output.pricing_method,
            )
            return output

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "pricing_agent: attempt %d failed — %s: %s",
                attempt, type(exc).__name__, exc,
            )
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"pricing_agent failed after {MAX_RETRIES} attempts "
                    f"for submission {submission_id}.\nLast error: {exc}\nResponse: {raw[:400]}"
                ) from exc
