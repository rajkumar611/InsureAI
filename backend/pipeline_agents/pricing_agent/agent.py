from __future__ import annotations

import json
import logging
from decimal import Decimal, ROUND_HALF_UP

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline_agents.document_ingestion_agent.schemas import SubmissionData
from pipeline_agents.human_in_the_loop.schemas import UnderwriterDecision
from pipeline_agents.pricing_agent.schemas import PaymentOption, PremiumDiscount, PremiumLoading, PricingOutput
from pipeline_agents.underwriting_risk_agent.schemas import RiskAssessment
from engine.cost_tracking.middleware import record_llm_cost
from engine.llm.client import anthropic_client, model_for
from engine.llm.parsing import extract_first_json_object
from engine.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "pricing_agent"
ACTUARIAL_TABLE_VERSION = "AI-UW-NZ-AU-PROP-2024-v1"
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
    return _MARKET_RATES.get(cob, {}).get(jurisdiction, _DEFAULT_RATES)


def _compute_premium(
    sum_insured: Decimal,
    rates: dict,
    risk_score: float,
    security_features: list[str],
    year_built: int | None,
    excess_requested: Decimal | None,
    mitigating_factors: list[str],
) -> dict:
    """Deterministic premium calculation — no LLM involved in any numeric output."""
    base = (sum_insured * Decimal(str(rates["base_rate_per_mille"])) / Decimal("1000")).quantize(Decimal("0.01"))

    risk_loadings: list[dict] = []
    if risk_score >= 0.60:
        amt = (base * Decimal("0.20")).quantize(Decimal("0.01"))
        risk_loadings.append({"reason": f"High risk score ({risk_score:.2f})", "amount": amt})
    elif risk_score >= 0.40:
        amt = (base * Decimal("0.10")).quantize(Decimal("0.01"))
        risk_loadings.append({"reason": f"Elevated risk score ({risk_score:.2f})", "amount": amt})

    features_str = " ".join(f.lower() for f in (security_features or []))
    mit_str = " ".join(m.lower() for m in (mitigating_factors or []))

    discounts: list[dict] = []
    if "sprinkler" in features_str:
        pct = Decimal(str(rates.get("sprinkler_discount_pct", 10)))
        discounts.append({"reason": "Automatic sprinkler system", "amount": (base * pct / 100).quantize(Decimal("0.01"))})
    if "alarm" in features_str or "monit" in features_str:
        pct = Decimal(str(rates.get("monitored_alarm_discount_pct", 5)))
        discounts.append({"reason": "Monitored alarm system", "amount": (base * pct / 100).quantize(Decimal("0.01"))})
    if "no claims" in mit_str or "zero claims" in mit_str or "0 claims" in mit_str:
        pct = Decimal(str(rates.get("no_claims_5yr_discount_pct", 10)))
        discounts.append({"reason": "No claims in 3 years", "amount": (base * pct / 100).quantize(Decimal("0.01"))})
    if year_built and year_built >= 2000:
        pct = Decimal(str(rates.get("post_2000_build_discount_pct", 5)))
        discounts.append({"reason": f"Post-2000 construction ({year_built})", "amount": (base * pct / 100).quantize(Decimal("0.01"))})

    total_loading = sum(item["amount"] for item in risk_loadings)
    total_discount = sum(item["amount"] for item in discounts)
    final = base + total_loading - total_discount

    currency = rates.get("currency", "NZD").lower()
    tech_min = Decimal(str(rates.get(f"technical_minimum_{currency}", 750)))
    if final < tech_min:
        final = tech_min
    final = final.quantize(Decimal("0.01"))

    # Excess = 10% of final premium, rounded to nearest 100 (min 100)
    raw_excess = final * Decimal("0.10")
    excess = max(
        (raw_excess / Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP) * Decimal("100"),
        Decimal("100"),
    )

    payment_options = [
        {"frequency": "ANNUAL", "instalment_amount": final, "total_amount": final},
        {"frequency": "QUARTERLY", "instalment_amount": (final / 4).quantize(Decimal("0.01")), "total_amount": final},
        {"frequency": "MONTHLY", "instalment_amount": (final / 12).quantize(Decimal("0.01")), "total_amount": final},
    ]

    return {
        "base_premium": base,
        "risk_loadings": risk_loadings,
        "claims_loadings": [],
        "discounts": discounts,
        "final_premium": final,
        "premium_currency": rates.get("currency", "NZD"),
        "excess_recommended": excess,
        "payment_options": payment_options,
    }



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

    # ── Step 1: compute all numbers deterministically in Python ──────────────
    computed = _compute_premium(
        sum_insured=submission_data.sum_insured or Decimal("0"),
        rates=rates,
        risk_score=float(risk_assessment.risk_score),
        security_features=list(submission_data.security_features),
        year_built=submission_data.year_built,
        excess_requested=submission_data.excess_requested,
        mitigating_factors=list(risk_assessment.mitigating_factors),
    )
    logger.info(
        "pricing_agent: deterministic computation complete  base=%s  final=%s  currency=%s",
        computed["base_premium"], computed["final_premium"], computed["premium_currency"],
    )

    # ── Step 2: call LLM only for qualitative text fields ────────────────────
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

    llm_text: dict = {}
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "pricing_agent: LLM rationale attempt %d/%d  submission=%s",
            attempt, MAX_RETRIES, submission_id,
        )

        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "The premium numbers have already been calculated. "
                        "Return ONLY a JSON object with these three fields: "
                        '{"premium_rationale": "...", "policy_conditions": [...], "exclusions": [...]}'
                    ),
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

        if not response.content:
            raise ValueError("LLM returned empty response")
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip()

        try:
            llm_text = json.loads(extract_first_json_object(raw))
            break
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("pricing_agent: rationale parse failed attempt %d — %s", attempt, exc)
            if attempt == MAX_RETRIES:
                llm_text = {}

    # ── Step 3: merge computed numbers with LLM text ─────────────────────────
    output = PricingOutput(
        submission_id=submission_id,
        base_premium=computed["base_premium"],
        risk_loadings=[PremiumLoading(**l) for l in computed["risk_loadings"]],
        claims_loadings=[],
        discounts=[PremiumDiscount(**d) for d in computed["discounts"]],
        final_premium=computed["final_premium"],
        premium_currency=computed["premium_currency"],
        excess_recommended=computed["excess_recommended"],
        payment_options=[PaymentOption(**p) for p in computed["payment_options"]],
        premium_rationale=llm_text.get("premium_rationale", ""),
        policy_conditions=llm_text.get("policy_conditions", []),
        exclusions=llm_text.get("exclusions", []),
        actuarial_table_version=ACTUARIAL_TABLE_VERSION,
        pricing_method="STANDARD",
    )
    logger.info(
        "pricing_agent: success  final_premium=%s %s",
        output.final_premium, output.premium_currency,
    )
    return output
