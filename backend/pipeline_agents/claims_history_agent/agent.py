from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline_agents.claims_history_agent.schemas import ClaimProfile
from pipeline_agents.document_ingestion_agent.schemas import SubmissionData
from engine.cost_tracking.middleware import record_llm_cost
from database.models import ClaimsEmbedding, Customer
from engine.llm.client import anthropic_client, model_for
from engine.llm.parsing import extract_first_json_object
from engine.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "claims_history_agent"
TOP_K = 8
MAX_RETRIES = 2

# ── Deterministic stats from raw records ──────────────────────────────────────
# The LLM writes risk_flags, data_quality, and qualitative rationale.
# All numeric/categorical fields that feed downstream scoring formulas are
# computed here in Python so identical DB results always yield identical outputs.


def _compute_stats_from_records(records: list[dict]) -> dict:
    """Derive deterministic numeric fields directly from raw claim records."""
    cutoff_3yr = _cutoff(3)
    cutoff_5yr = _cutoff(5)

    amounts_3yr: list[Decimal] = []
    amounts_3to5yr: list[Decimal] = []
    amounts_all: list[Decimal] = []

    for rec in records:
        amount = Decimal(str(rec["incurred_amount"])) if rec.get("incurred_amount") else Decimal("0")
        amounts_all.append(amount)

        claim_date: datetime | None = None
        if rec.get("claim_date"):
            try:
                claim_date = datetime.fromisoformat(str(rec["claim_date"]))
                if claim_date.tzinfo is None:
                    claim_date = claim_date.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        if claim_date and claim_date >= cutoff_5yr:
            if claim_date >= cutoff_3yr:
                amounts_3yr.append(amount)
            else:
                amounts_3to5yr.append(amount)

    count_3yr = len(amounts_3yr)
    count_5yr = count_3yr + len(amounts_3to5yr)

    # Frequency trend: annualised rate recent 3yr vs prior 2yr window
    annual_recent = count_3yr / 3.0
    annual_prior = len(amounts_3to5yr) / 2.0
    if count_3yr == 0 and len(amounts_3to5yr) == 0:
        trend = "INSUFFICIENT_DATA"
    elif len(amounts_3to5yr) == 0:
        trend = "INCREASING" if count_3yr >= 2 else "INSUFFICIENT_DATA"
    elif annual_recent > annual_prior * 1.25:
        trend = "INCREASING"
    elif annual_recent < annual_prior * 0.75:
        trend = "DECREASING"
    else:
        trend = "STABLE"

    return {
        "total_claims_3yr": count_3yr,
        "total_claims_5yr": count_5yr,
        "total_incurred_3yr": sum(amounts_3yr, Decimal("0")),
        "total_incurred_5yr": sum(amounts_3yr + amounts_3to5yr, Decimal("0")),
        "largest_single_loss": max(amounts_all, default=Decimal("0")),
        "claim_frequency_trend": trend,
    }


def _deterministic_data_quality(retrieval_source: str, record_count: int) -> str:
    if retrieval_source == "CUSTOMER_HISTORY":
        if record_count >= 3:
            return "HIGH"
        return "MEDIUM" if record_count >= 1 else "LOW"
    return "MEDIUM" if record_count >= 5 else "LOW"


def _deterministic_profile_confidence(retrieval_source: str, record_count: int) -> float:
    if retrieval_source == "CUSTOMER_HISTORY":
        return round(min(0.90, 0.70 + record_count * 0.05), 2)
    return round(min(0.70, 0.50 + record_count * 0.025), 2)

# ── Embedding model (loaded once per process) ─────────────────────────────────

@lru_cache(maxsize=1)
def _get_encoder():
    from sentence_transformers import SentenceTransformer
    logger.info("claims_history_agent: loading sentence-transformers model")
    return SentenceTransformer("all-MiniLM-L6-v2")




def _embed(text_: str) -> list[float]:
    return _get_encoder().encode(text_).tolist()


# ── Customer lookup ───────────────────────────────────────────────────────────

async def _find_customer_id(
    submission_data: SubmissionData,
    session: AsyncSession,
) -> str | None:
    """Return customer_id UUID string if a matching customer is found, else None."""
    # 1. Try NZBN / ABN exact match
    if submission_data.insured_abn_or_registration:
        row = await session.execute(
            select(Customer).where(
                Customer.abn_nzbn == submission_data.insured_abn_or_registration
            )
        )
        customer = row.scalars().first()
        if customer:
            logger.info("claims_history_agent: customer matched by ABN/NZBN → %s", customer.customer_ref)
            return str(customer.id)

    # 2. Fallback — case-insensitive name match
    if submission_data.insured_name:
        row = await session.execute(
            select(Customer).where(
                Customer.full_name.ilike(f"%{submission_data.insured_name}%")
            )
        )
        customer = row.scalars().first()
        if customer:
            logger.info("claims_history_agent: customer matched by name → %s", customer.customer_ref)
            return str(customer.id)

    return None


# ── Claims retrieval ──────────────────────────────────────────────────────────

async def _fetch_customer_claims(
    customer_id: str,
    class_of_business: str,
    session: AsyncSession,
) -> list[dict]:
    """Fetch all claims_embeddings rows for this customer."""
    rows = await session.execute(
        select(ClaimsEmbedding).where(
            ClaimsEmbedding.customer_id == customer_id,
            ClaimsEmbedding.class_of_business == class_of_business,
        )
    )
    return [_row_to_dict(r) for r in rows.scalars().all()]


async def _fetch_similar_claims(
    submission_data: SubmissionData,
    class_of_business: str,
    jurisdiction: str,
    session: AsyncSession,
) -> list[dict]:
    """Vector similarity search — returns TOP_K most similar claims."""
    query_text = (
        f"{submission_data.insured_name or ''} "
        f"property insurance {submission_data.risk_address or ''} "
        f"{class_of_business}"
    )
    vec = _embed(query_text)
    # Build a strictly numeric literal — float() raises if any value is not a real number
    vec_literal = "[" + ",".join(f"{float(v):.8g}" for v in vec) + "]"

    result = await session.execute(
        text("""
            SELECT id, claim_id, customer_ref, risk_address_region,
                   class_of_business, jurisdiction, claim_date, cause_of_loss,
                   incurred_amount, currency, is_large_loss, fraud_flag, claim_summary,
                   1 - (embedding <=> CAST(:vec AS vector)) AS similarity
            FROM claims_embeddings
            WHERE class_of_business = :cob
              AND jurisdiction = :jur
              AND fraud_flag = false
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :top_k
        """),
        {"vec": vec_literal, "cob": class_of_business, "jur": jurisdiction, "top_k": TOP_K},
    )
    rows = result.mappings().all()
    return [dict(r) for r in rows]


def _row_to_dict(row: ClaimsEmbedding) -> dict:
    return {
        "claim_id": str(row.claim_id) if row.claim_id else None,
        "customer_ref": row.customer_ref,
        "risk_address_region": row.risk_address_region,
        "class_of_business": row.class_of_business,
        "jurisdiction": row.jurisdiction,
        "claim_date": row.claim_date.isoformat() if row.claim_date else None,
        "cause_of_loss": row.cause_of_loss,
        "incurred_amount": str(row.incurred_amount) if row.incurred_amount else None,
        "currency": row.currency,
        "is_large_loss": row.is_large_loss,
        "fraud_flag": row.fraud_flag,
        "claim_summary": row.claim_summary,
    }


# ── Threshold for "recent" claims ─────────────────────────────────────────────

def _cutoff(years: int) -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(year=now.year - years)


# ── Main entry point ──────────────────────────────────────────────────────────

async def run(
    *,
    submission_id: str,
    submission_data: SubmissionData,
    class_of_business: str,
    jurisdiction: str,
    session: AsyncSession,
) -> ClaimProfile:
    """
    Retrieve claims history for the submission and analyse with Claude Haiku.

    Strategy:
      1. Match customer by NZBN/ABN or name → CUSTOMER_HISTORY
      2. If no customer match → vector similarity on same class/jurisdiction → BENCHMARK
      3. If customer matched but has no claims → vector search → BENCHMARK
    """
    customer_id = await _find_customer_id(submission_data, session)

    if customer_id:
        records = await _fetch_customer_claims(customer_id, class_of_business, session)
        if records:
            retrieval_source = "CUSTOMER_HISTORY"
        else:
            logger.info("claims_history_agent: customer found but no claims — falling back to BENCHMARK")
            records = await _fetch_similar_claims(submission_data, class_of_business, jurisdiction, session)
            retrieval_source = "BENCHMARK"
    else:
        logger.info("claims_history_agent: no customer match — using BENCHMARK similarity search")
        records = await _fetch_similar_claims(submission_data, class_of_business, jurisdiction, session)
        retrieval_source = "BENCHMARK"

    logger.info(
        "claims_history_agent: %d records retrieved  source=%s  submission=%s",
        len(records), retrieval_source, submission_id,
    )

    if not records:
        # No data at all — return a minimal NO_HISTORY profile without calling LLM
        logger.warning("claims_history_agent: no claims data available for submission %s", submission_id)
        return ClaimProfile(
            submission_id=submission_id,
            source="BENCHMARK",
            risk_flags=["NO_HISTORY"],
            confidence=0.0,
            data_quality="LOW",
        )

    # ── Call Claude Haiku ─────────────────────────────────────────────────────
    prompt_template = PromptRegistry.load(AGENT_NAME)
    model = model_for(AGENT_NAME)

    system_prompt = prompt_template.render(
        submission_id=submission_id,
        insured_name=submission_data.insured_name or "Unknown",
        risk_address=submission_data.risk_address or "Unknown",
        class_of_business=class_of_business,
        retrieval_source=retrieval_source,
        retrieved_claims_records=json.dumps(records, indent=2, default=str),
    )

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "claims_history_agent: LLM attempt %d/%d  submission=%s",
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
                    "content": "Analyse the retrieved claims records and produce the ClaimProfile JSON.",
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
            feature_tag="claims_rag",
        )

        if not response.content:
            raise ValueError("LLM returned empty response")
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(extract_first_json_object(raw))
            # Normalise common LLM field-name variations before Pydantic sees them
            if "source" not in data:
                data["source"] = data.pop("data_source", retrieval_source)
            # Always override with the values we know to be correct
            data["submission_id"] = submission_id
            data["source"] = retrieval_source
            # Drop any extra fields Claude invented that aren't in the schema
            allowed = ClaimProfile.model_fields.keys()
            data = {k: v for k, v in data.items() if k in allowed}
            profile = ClaimProfile.model_validate(data)

            # Override LLM-generated numeric/categorical fields with deterministic
            # values computed directly from DB records, so identical inputs always
            # produce identical downstream risk and confidence scores.
            stats = _compute_stats_from_records(records)
            profile.total_claims_3yr = stats["total_claims_3yr"]
            profile.total_claims_5yr = stats["total_claims_5yr"]
            profile.total_incurred_3yr = stats["total_incurred_3yr"]
            profile.total_incurred_5yr = stats["total_incurred_5yr"]
            profile.largest_single_loss = stats["largest_single_loss"]
            profile.claim_frequency_trend = stats["claim_frequency_trend"]
            profile.data_quality = _deterministic_data_quality(retrieval_source, len(records))
            profile.confidence = _deterministic_profile_confidence(retrieval_source, len(records))

            logger.info(
                "claims_history_agent: success  flags=%s  confidence=%.2f  source=%s",
                profile.risk_flags, profile.confidence, profile.source,
            )
            return profile

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "claims_history_agent: attempt %d failed — %s: %s",
                attempt, type(exc).__name__, exc,
            )
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"claims_history_agent failed after {MAX_RETRIES} attempts "
                    f"for submission {submission_id}.\nLast error: {exc}\nResponse: {raw[:400]}"
                ) from exc
