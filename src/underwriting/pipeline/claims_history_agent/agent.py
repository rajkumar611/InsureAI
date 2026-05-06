from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from underwriting.pipeline.claims_history_agent.schemas import ClaimProfile
from underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from underwriting.platform.cost_tracking.middleware import record_llm_cost
from underwriting.platform.database.models import ClaimsEmbedding, Customer
from underwriting.platform.llm.client import anthropic_client, model_for
from underwriting.platform.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "claims_history_agent"
TOP_K = 8
MAX_RETRIES = 2

# ── Embedding model (loaded once per process) ─────────────────────────────────

@lru_cache(maxsize=1)
def _get_encoder():
    from sentence_transformers import SentenceTransformer
    logger.info("claims_history_agent: loading sentence-transformers model")
    return SentenceTransformer("all-MiniLM-L6-v2")


def _extract_first_json_object(text: str) -> str:
    """Return the first complete {...} block from text, ignoring trailing commentary."""
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
    vec_literal = f"[{','.join(str(v) for v in vec)}]"

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

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(_extract_first_json_object(raw))
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
