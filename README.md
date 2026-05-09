# AI Underwriting System

> **Enterprise-grade multi-agent AI pipeline for property insurance underwriting — built on LangGraph, Claude, pgvector, FastAPI, and Streamlit.**

An end-to-end intelligent underwriting platform that ingests broker submissions, evaluates risk through parallel specialist agents, enforces deterministic pre-screen rules, supports human-in-the-loop review, prices accepted policies, and gates every decision through a compliance governance layer — all with full cost tracking and an immutable audit trail.

---

## Table of Contents

- [Why This Architecture](#why-this-architecture)
- [System Architecture](#system-architecture)
- [Agent Pipeline](#agent-pipeline)
- [LangGraph Orchestration](#langgraph-orchestration)
- [Key Technical Features](#key-technical-features)
  - [Prompt Injection Defence](#prompt-injection-defence)
  - [Parallel Agent Execution](#parallel-agent-execution)
  - [Deterministic Pre-Screening](#deterministic-pre-screening)
  - [RAG with pgvector](#rag-with-pgvector)
  - [Human-in-the-Loop](#human-in-the-loop)
  - [LLM Cost Tracking](#llm-cost-tracking)
  - [Immutable Audit Trail](#immutable-audit-trail)
  - [Versioned Prompt Registry](#versioned-prompt-registry)
  - [Governance and Compliance Gate](#governance-and-compliance-gate)
- [Model Routing Strategy](#model-routing-strategy)
- [Database Design](#database-design)
- [API Reference](#api-reference)
- [Tech Stack](#tech-stack)
- [Running Locally](#running-locally)
- [Testing](#testing)
- [Sample Documents](#sample-documents)
- [Project Structure](#project-structure)

---

## Why This Architecture

Insurance underwriting is a domain where **wrong answers have real financial consequences**. This system is designed around three principles:

1. **Determinism over delegation** — Risk thresholds, scoring formulas, and pre-screen rules are implemented in Python, not left to LLM judgement. LLMs handle synthesis and natural-language reasoning; Python handles arithmetic and boolean logic.

2. **No silent failures** — Every agent decision is recorded with its input, output, prompt version, and confidence score. The audit trail uses forward hash-chaining so any tampering is detectable.

3. **Human escalation is rule-triggered** — The system never decides on its own to skip human review. Escalation criteria are explicit code conditions, not emergent LLM behaviour.

---

## System Architecture

```
BROKER SUBMISSION
      |
      v
+-------------------------------------------------------------+
|  POST /api/v1/submissions/pipeline                          |
|  FastAPI · Prompt-injection gate · Daily spend cap          |
+----------------------+--------------------------------------+
                       |
                       v
        +--------------------------+
        |  Document Ingestion      |  Claude Haiku
        |  Extract · Validate      |  Pydantic SubmissionData
        |  Anomaly Detection       |  Prompt-injection detection
        +-------------+------------+
                      |
          LangGraph StateGraph starts
                      |
         +------------+------------+
         |   parallel_analysis     |  asyncio.gather()
         |  (single LangGraph node)|
         +------------+------------+
              |                |
              v                v
     +--------------+   +--------------+
     |  Claims      |   |  Hazard      |
     |  History     |   |  Evaluation  |
     |  Agent       |   |  Agent       |
     | Haiku + RAG  |   |  Sonnet      |
     +------+-------+   +-------+------+
            +--------+----------+
                     |
                     v
       +---------------------------+
       |  Underwriting Risk        |  Claude Sonnet
       |  Pre-screen --> Synthesis |  ACCEPT / DECLINE / REFER
       +-----------+---------------+
                   |
       +-----------+-------------------------+
       |   route_after_risk()                |
       |   DECLINE ---------> decline node   |
       |   REFER or conf<0.70               |
       |     --> human_review + HITL         |
       |   ACCEPT + conf>=0.70              |
       |     --> auto_approve               |
       +-----------+-------------------------+
                   |
       +-----------v-----------+
       |   Pricing Agent       |  Claude Haiku
       |   Python numerics     |  LLM for rationale only
       +-----------+-----------+
                   |
       +-----------v-----------+
       |  Governance Agent     |  Claude Sonnet · 4096 tokens
       |  Final compliance     |  APPROVED / REJECTED / REFER
       |  gate                 |
       +-----------------------+

Cross-cutting every node:
  Cost Tracker  -->  cost_ledger table (append-only)
  Audit Trail   -->  audit_trail table (hash-chained, immutable)
```

---

## Agent Pipeline

### Agent 1 — Document Ingestion

**Model:** `claude-haiku-4-5-20251001` · **Max tokens:** 2 048 · **Temperature:** 0

The entry point for every broker submission. Responsibilities:

- Extracts 24 structured fields into a `SubmissionData` Pydantic model (insured name, risk address, sum insured, coverage type, policy period, construction type, year built, floor area, occupancy, existing security features, prior claims disclosure, etc.)
- Maps extraction confidence to numeric scores: `high -> 0.90`, `medium -> 0.70`, `low -> 0.50`
- Detects anomalies including prompt-injection attempts (see [Prompt Injection Defence](#prompt-injection-defence))
- Retries up to **2 times** on `json.JSONDecodeError` or Pydantic `ValidationError`; raises `RuntimeError` with full context on exhaustion

Mandatory fields enforced at the API layer before any LLM call: `insured_name`, `risk_address`, `sum_insured`, `coverage_type`, `policy_period_start`, `policy_period_end`.

---

### Agent 2 — Claims History (RAG)

**Model:** `claude-haiku-4-5-20251001` · **Embedding:** `all-MiniLM-L6-v2` (384-dim)

Builds a structured claims profile using a **three-tier deterministic customer matching** strategy:

| Tier | Method | Condition |
|------|--------|-----------|
| 1 | ABN / NZBN exact match | `Customer.abn_nzbn == submission_data.insured_abn_or_registration` |
| 2 | Name fuzzy match | `Customer.full_name ILIKE '%{insured_name}%'` |
| 3 | pgvector similarity | Falls through to benchmark when no customer or zero claims |

When a customer is found, recent claim records are fetched and enriched. When not, the agent performs a **RAG vector search** against benchmark claims from similar businesses:

```sql
SELECT *,
  1 - (embedding <=> CAST(:vec AS vector)) AS similarity
FROM claims_embeddings
WHERE class_of_business = :cob
  AND jurisdiction      = :jur
  AND fraud_flag        = false
ORDER BY embedding <=> CAST(:vec AS vector)
LIMIT 8;
```

The embedding query string is: `"{insured_name} property insurance {risk_address} {class_of_business}"` — encoded locally via `SentenceTransformer` (loaded once with `@lru_cache`) and formatted as a pgvector literal.

All statistical aggregations — total claims (3yr / 5yr), total incurred, largest single loss, trend direction — are **computed in Python**, not delegated to the LLM:

- **Trend:** `INCREASING` if `recent_annual / prior_annual > 1.25`, `DECREASING` if `< 0.75`, else `STABLE`
- **Data quality:** `HIGH` (>= 3 customer records), `MEDIUM` (>= 1), `LOW` (benchmark fallback)
- **Confidence:** `min(0.90, 0.70 + count * 0.05)` for customer history; `min(0.70, 0.50 + count * 0.025)` for benchmark

---

### Agent 3 — Hazard Evaluation

**Model:** `claude-sonnet-4-6`

Evaluates the property's physical and geographic risk across five dimensions: seismic, flood, fire, weather, and industrial proximity.

**Geographic keyword tables** map risk addresses to hazard levels for NZ and AU:

| Region | Zone | Level |
|--------|------|-------|
| Wellington / Wairarapa / Kaikoura | Seismic | HIGH |
| Christchurch / Napier | Seismic | MEDIUM |
| Hawke's Bay / Napier / Hastings | Flood | HIGH |
| Cairns / Townsville / Darwin | Cyclone | HIGH |
| Coastal keywords (waterfront, harbour, esplanade) | Coastal | elevated |
| Industrial keywords (warehouse, factory, refinery) | Industrial | elevated |

**Deterministic overrides replace LLM-generated floats** before the score is returned:

```python
score.overall_hazard_score = _HAZARD_SCORE_MAP[score.overall_hazard_level]
# EXTREME->0.90, HIGH->0.70, MEDIUM->0.45, LOW->0.20, NEGLIGIBLE->0.05

score.data_gaps = _deterministic_data_gaps(submission_data)
# Flags missing: construction_type, year_built, gross_floor_area_sqm, occupancy_type

score.confidence = max(0.50, min(0.95, 0.90 - len(gaps) * 0.05))
# Each missing field reduces confidence by 5 percentage points
```

This ensures that two submissions with identical inputs always produce identical numeric scores — the LLM cannot introduce float variance into routing decisions.

---

### Agent 4 — Underwriting Risk Assessment

**Model:** `claude-sonnet-4-6`

The primary decision agent. Runs a **deterministic pre-screen before any LLM call**; if a rule fires, the agent returns immediately with `pre_screen_triggered=True` and `confidence_score=1.0`.

#### Pre-Screen Rules

| Condition | Action |
|-----------|--------|
| `hazard_level == EXTREME` AND `total_claims_3yr > 2` | **DECLINE** · `risk_score=0.95` |
| `"FRAUD_SUSPICION"` in `claim_profile.risk_flags` | **DECLINE** · `risk_score=0.95` |
| `sum_insured > NZD/AUD 50,000,000` | **REFER** · `risk_score=0.80` |
| `hazard_score.confidence < 0.50` | **REFER** · `risk_score=0.80` |
| `extraction_confidence == "low"` | **REFER** · `risk_score=0.80` |

Note: `claim_data_quality == "LOW"` is **not** a hard pre-screen — it penalises the confidence score (−0.15) and is passed to the LLM for nuanced judgment alongside the full submission context.

#### Risk Score Formula (when pre-screen does not fire)

```python
base         = HAZARD_BASE_SCORE[hazard_level]     # EXTREME:0.85, HIGH:0.65, MEDIUM:0.40, LOW:0.20
claims_adj   = min(total_claims_3yr * 0.05, 0.20)
large_loss   = 0.05 if largest_single_loss > 200_000 else 0.0
trend_adj    = {INCREASING: +0.05, STABLE: 0.0, DECREASING: -0.03, INSUFFICIENT_DATA: +0.02}
risk_score   = min(0.99, max(0.01, base + claims_adj + large_loss + trend_adj))
```

#### Confidence Score Formula

```python
conf  = 0.92
conf -= 0.15 if claim_data_quality == "LOW" else (0.05 if "MEDIUM" else 0)
conf -= len(hazard_data_gaps) * 0.04
conf -= 0.10 if signal_conflict else 0      # e.g. HIGH hazard + clean claims
conf -= 0.10 if extraction_confidence == "low" else (0.03 if "medium" else 0)
conf  = max(0.50, min(0.98, conf))
```

Signal conflicts (e.g. low hazard + risky claims history, or high hazard + perfect claims record) are detected and penalise confidence, triggering human review.

When pre-screen does not fire, Claude Sonnet synthesises all agent outputs into a final `ACCEPT / DECLINE / REFER` decision with supporting rationale.

---

### Agent 5 — Human-in-the-Loop (HITL)

For referrals, the LangGraph workflow calls `interrupt()` to **suspend the graph at a checkpoint**, persisting full state to PostgreSQL. The underwriter is presented with:

- Complete risk assessment snapshot
- Claims profile and hazard breakdown
- Recommended decision with confidence scores
- Full submission extracted data

**Priority rules:**

| Risk Score | Priority |
|------------|----------|
| >= 0.80 | HIGH |
| >= 0.60 | STANDARD |
| < 0.60 | LOW |

**SLA deadline rules:**

| Risk Score | SLA |
|------------|-----|
| >= 0.75 | 2 business days |
| < 0.75 | 5 business days |

Underwriter decisions: `APPROVE`, `APPROVE_WITH_CONDITIONS`, `OVERRIDE`, `DECLINE`, `REQUEST_ADDITIONAL_INFO`, `REQUEST_SURVEY`.

Resuming the pipeline: `POST /api/v1/queue/{queue_id}/decision` calls `resume_pipeline(thread_id, decision)`, which issues `graph.ainvoke(Command(resume=decision_data), config={"configurable": {"thread_id": submission_id}})` — the graph resumes from exactly the interrupted node.

---

### Agent 6 — Pricing

**Model:** `claude-haiku-4-5-20251001` · **Actuarial Table:** `AI-UW-NZ-AU-PROP-2024-v1`

Premium calculation is **entirely deterministic Python**; the LLM only generates the premium rationale text.

```python
# NZ Commercial Property — simplified illustration
base        = sum_insured * 1.20 / 1_000          # 1.20 per mille base rate
risk_load   = base * 0.20 if risk_score >= 0.60 else base * 0.10
discounts   = (
    base * 0.10 if sprinkler_system   else 0 +
    base * 0.05 if monitored_alarm    else 0 +
    base * 0.10 if no_claims_5yr      else 0 +
    base * 0.05 if year_built >= 2000 else 0
)
premium     = max(750, base + risk_load - discounts)
excess      = max(100, round(premium * 0.10 / 100) * 100)
```

Payment options (annual, quarterly, monthly) are computed as exact divisions — no rounding variance.

---

### Agent 7 — Governance

**Model:** `claude-sonnet-4-6` · **Max tokens:** 4 096 · **Compliance rules:** `AI-UW-COMPLIANCE-NZ-AU-2024-v1`

The final gatekeeper. Reviews the entire workflow chain for:

- Internal consistency (risk score vs. premium vs. decision alignment)
- Fraud signals missed by earlier agents
- Regulatory compliance (RBNZ/FMA for NZ; APRA for AU)
- Data quality adequacy for the sum insured level

**Outcomes:** `APPROVED` -> `workflow_status=COMPLETED` | `REFER_TO_SENIOR_UNDERWRITER` -> `AWAITING_SENIOR_REVIEW` | `REJECTED` -> `GOVERNANCE_REJECTED`

---

## LangGraph Orchestration

The workflow is implemented as a **LangGraph `StateGraph`** with typed state, conditional routing, interrupt/resume support, and PostgreSQL checkpointing.

### WorkflowState

```python
class WorkflowState(TypedDict):
    submission_id:        str
    class_of_business:    str
    jurisdiction:         str
    submission_data:      dict   # SubmissionData serialised
    claim_profile:        dict   # ClaimsProfile serialised
    hazard_score:         dict   # HazardScore serialised
    risk_assessment:      dict   # RiskAssessment serialised
    underwriter_decision: dict   # UnderwriterDecision serialised
    pricing_output:       dict   # PricingOutput serialised
    governance_decision:  dict   # GovernanceDecision serialised
    workflow_status:      str    # RUNNING|AWAITING_HUMAN|COMPLETED|DECLINED|FAILED
    error:                str | None
```

All values are JSON-serialisable — no SQLAlchemy sessions, no live objects in state. Each node reconstructs what it needs from the dict.

### Node Graph

```
START
  └─> parallel_analysis
        (asyncio.gather: claims + hazard)
  └─> underwriting_risk
        └─> route_after_risk()
              |-- DECLINE ──────────────────────> decline ──> END
              |-- REFER or confidence < 0.70 ──> human_review
              |                                     └─> interrupt()
              |                                     ^
              |                           POST /queue/{id}/decision
              |                           Command(resume=decision)
              └-- ACCEPT + confidence >= 0.70 ─> auto_approve
                                                    |
                                       +------------+
                                       v
                                     pricing
                                       └─> governance ──> END
```

### Checkpointing

```python
checkpointer = PostgresSaver(
    ConnectionPool(
        conninfo=DATABASE_URL,
        max_size=5,
        open=False,
    )
)
graph = workflow.compile(checkpointer=checkpointer)
```

`thread_id = submission_id` — every submission has its own checkpoint thread. This enables cross-request pause/resume: the API server can restart between the initial submission and the underwriter's decision, and the workflow resumes correctly.

The checkpointer uses the **sync `psycopg3` driver** (not async) to avoid Windows `ProactorEventLoop` incompatibility with the async psycopg3 driver. LangGraph dispatches sync checkpoint calls via a thread pool executor automatically.

---

## Key Technical Features

### Prompt Injection Defence

Broker documents are **untrusted input** processed in two independent layers:

**Layer 1 — API Gate (before any LLM call):**

```python
_INJECTION_KEYWORDS = (
    "injection", "ignore previous", "disregard your", "unrestricted mode",
)

def _contains_injection(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _INJECTION_KEYWORDS)
```

If detected, the submission is immediately declined with `decline_reason="PROMPT_INJECTION"` — the document never reaches Claude.

**Layer 2 — LLM Prompt Instruction:**

The ingestion prompt instructs Claude to flag anomalies including injection patterns. Anomaly keywords in the LLM response are checked against the same keyword list, and any match is recorded in the audit trail.

This defence-in-depth approach means a submission rejected at layer 1 never consumes LLM tokens, while layer 2 catches patterns that the keyword filter might miss.

---

### Parallel Agent Execution

Claims history and hazard evaluation have no data dependency on each other — they both read from `submission_data` only. The LangGraph `parallel_analysis_node` runs them concurrently:

```python
async def parallel_analysis_node(state: WorkflowState) -> WorkflowState:
    claim_profile, hazard_score = await asyncio.gather(
        claims_agent.run(submission_id, submission_data, session),
        hazard_agent.run(submission_id, submission_data, session),
    )
    return {**state, "claim_profile": claim_profile, "hazard_score": hazard_score}
```

This halves the wall-clock time for the most latency-sensitive part of the pipeline, as both agents involve LLM API calls and database operations.

---

### Deterministic Pre-Screening

Pre-screen logic fires **before** any underwriting LLM call. The philosophy: if the answer is already clear from the data, spending tokens on synthesis is wasteful and introduces variance.

The pre-screen path returns `pre_screen_triggered=True` and `confidence_score=1.0` — maximum confidence because the rule fired unconditionally, not because the LLM was confident.

The LLM is only invoked for the genuinely ambiguous middle-ground submissions where synthesis and judgement are needed.

---

### RAG with pgvector

pgvector is loaded as a PostgreSQL extension in migration `0001`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The `claims_embeddings` table stores 384-dimensional vectors with an HNSW index for approximate nearest-neighbour search:

```python
class ClaimsEmbedding(Base):
    embedding = mapped_column(Vector(384))

# Migration creates the HNSW index:
# CREATE INDEX ON claims_embeddings
#   USING hnsw (embedding vector_cosine_ops)
#   WITH (m=16, ef_construction=64);
```

The embedding model (`all-MiniLM-L6-v2`) is loaded once per process via `@lru_cache(maxsize=1)` — no per-request model loading overhead. Vectors are serialised as pgvector literals `[v1,v2,...,v384]` and cast in SQL to avoid any ORM serialisation ambiguity.

**Why cosine distance for insurance claims?** Claims benchmark embeddings represent semantic similarity of risk profiles. Cosine distance measures directional similarity regardless of vector magnitude, which is appropriate for sentence-transformer outputs where magnitude is not meaningful.

---

### Human-in-the-Loop

LangGraph's `interrupt()` primitive is used — not a custom polling mechanism:

```python
async def human_review_node(state: WorkflowState) -> WorkflowState:
    queue_item = await hitl_agent.enqueue(state, session)
    decision_data = interrupt({
        "queue_id":          str(queue_item.id),
        "submission_id":     state["submission_id"],
        "risk_score":        state["risk_assessment"]["risk_score"],
        "escalation_reason": state["risk_assessment"]["escalation_reason"],
        "message":           "Awaiting underwriter review",
    })
    # Execution resumes here after Command(resume=decision_data)
    ...
```

The interrupt payload is persisted in the PostgreSQL checkpoint. The API server returns `workflow_status=AWAITING_HUMAN` to the caller. When the underwriter submits a decision via REST, the pipeline resumes from the exact checkpoint — even across server restarts.

---

### LLM Cost Tracking

Every LLM call is followed by a cost record written to `cost_ledger`:

```python
# Pricing per 1M tokens (USD)
PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
}

cost_usd = (
    input_tokens  / 1_000_000 * PRICING[model]["input"] +
    output_tokens / 1_000_000 * PRICING[model]["output"]
)
```

The `cost_ledger` table is append-only and tagged with: `submission_id`, `agent_name`, `model_id`, `prompt_version`, `feature_tag`, `class_of_business`, `jurisdiction`, `latency_ms`.

The **Streamlit cost dashboard** aggregates this into:
- Total spend, LLM call count, input/output token totals
- Cost breakdown by agent, by model, by class of business, by jurisdiction
- Daily spend trend chart
- Token efficiency metrics (avg tokens per call, avg cost per agent)
- Raw ledger table (last 100 rows)
- **Daily spend cap enforcement** — the pipeline API returns HTTP 429 if the daily total exceeds `DAILY_SPEND_CAP_USD` (default $10)

---

### Immutable Audit Trail

Every agent decision is written to `audit_trail` with:

```
agent_name | event_type | prompt_version | decision_value | confidence_score
parsed_output (JSONB) | entry_hash | previous_hash
```

Hash-chaining: `entry_hash = SHA256(previous_hash + agent_name + event_type + decision_value + timestamp)`. Any retroactive modification of a record breaks the chain, making tampering detectable.

This provides a complete, ordered, cryptographically linked record of every AI decision made for every submission — essential for regulatory review and model auditing.

---

### Versioned Prompt Registry

Prompts are stored as Markdown files with YAML frontmatter in `prompts/{agent}/v{major}.{minor}.md`:

```markdown
---
version: 1.0
agent: document-ingestion-agent
status: active
input_variables:
  - DOCUMENT_CONTENT: raw broker document text
  - SUBMISSION_ID: UUID for this submission
output_schema: SubmissionData
---

You are an expert insurance document analyst...
Extract the following fields from the broker document: {{DOCUMENT_CONTENT}}
```

The registry resolves `"latest"` by sorting version files numerically and selecting the highest `status: active` version. Templates use `{{VARIABLE_NAME}}` placeholders; unresolved variables raise `ValueError` at render time, preventing silent prompt truncation.

Prompts are cached: `@lru_cache(maxsize=64)`. Every audit trail record stores `prompt_version`, enabling precise replay of any historical decision.

---

### Governance and Compliance Gate

The governance agent is the only agent that receives the **complete workflow output** — submission data, claims profile, hazard score, risk assessment, underwriter decision, and pricing output. It checks:

- Internal consistency: does the premium reflect the risk score? does the underwriter decision align with the risk assessment?
- Fraud signals: cross-references claim flags against submission anomalies
- Regulatory compliance: RBNZ/FMA requirements for NZ policies; APRA requirements for AU policies
- Data quality adequacy: flags submissions where sum insured is high but data confidence is low

No policy is issued without a governance `APPROVED` outcome.

---

## Model Routing Strategy

| Agent | Model | Rationale |
|-------|-------|-----------|
| Document Ingestion | `claude-haiku-4-5-20251001` | Structured extraction — speed and cost optimised |
| Claims History | `claude-haiku-4-5-20251001` | LLM role is minimal; Python does the aggregation |
| Hazard Evaluation | `claude-sonnet-4-6` | Geographic and environmental reasoning benefits from deeper context |
| Underwriting Risk | `claude-sonnet-4-6` | Core decision synthesis — highest stakes, best model |
| Pricing | `claude-haiku-4-5-20251001` | Numerics are Python; LLM writes rationale text only |
| Governance | `claude-sonnet-4-6` | Cross-chain compliance review — needs full reasoning capability |

All model IDs are overridable via environment variables (`MODEL_INGESTION`, `MODEL_HAZARD`, etc.). The shared `AsyncAnthropic` client enforces rate limits: 50 requests/min, 200 000 tokens/min.

**Approximate cost per submission:**

| Path | Estimated Cost (USD) |
|------|---------------------|
| Pre-screen decline (Haiku only, no Sonnet calls) | ~$0.001 |
| Auto-approve (full pipeline) | ~$0.004–0.008 |
| HITL path (referral + governance reasoning) | ~$0.006–0.012 |

---

## Database Design

PostgreSQL 17 + pgvector, managed via Alembic migrations with async SQLAlchemy 2.0.

### Core Tables

| Table | Purpose | Key Design |
|-------|---------|------------|
| `submissions` | Central submission record | `status` enum, `extracted_data JSONB` |
| `customers` | KYC and entity data | `kyc_status`, `is_blacklisted`, `abn_nzbn` unique |
| `workflows` | LangGraph state and lineage | `state_snapshot JSONB`, `current_node` |
| `policies` | Issued policies | `policy_number` unique, `sum_insured Numeric` |
| `claims` | Historical claims | `fraud_flag`, indexed by `customer_id + claim_date` |
| `claims_embeddings` | pgvector store | `embedding Vector(384)`, HNSW index |
| `underwriter_queue` | HITL work queue | `sla_deadline`, `priority`, `pipeline_state_snapshot JSONB` |
| `audit_trail` | Immutable decision log | `entry_hash`, `previous_hash`, append-only |
| `cost_ledger` | LLM token costs | Per-call token counts and USD cost, append-only |
| `regulations` | Compliance rules | Versioned NZ/AU regulatory text — queried by governance agent |

### Migrations

| ID | Changes |
|----|---------|
| `0001_initial_schema` | Creates all platform tables; `CREATE EXTENSION vector`; initial `Vector(1536)` |
| `0002_resize_embedding_vector` | Resizes to `Vector(384)`; recreates HNSW index (`m=16, ef_construction=64`) |
| `0003_customers_policies_claims` | Adds `customers`, `policies`, `claims` with FK relationships |
| `0004_submission_extracted_data` | Adds `extracted_data`, `ingestion_confidence`, `ingestion_anomalies`, `missing_fields` to `submissions` |
| `0005_queue_pipeline_state` | Adds `pipeline_state_snapshot JSONB` to `underwriter_queue` for full HITL context |

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/health/ready` | Readiness check — DB connectivity |
| `POST` | `/api/v1/submissions` | Create submission record (no pipeline) |
| `GET` | `/api/v1/submissions/{ref}` | Fetch submission by policy number or UUID |
| `GET` | `/api/v1/submissions/{submission_id}/progress` | Real-time pipeline progress |
| `POST` | `/api/v1/submissions/ingest` | Document ingestion only — no workflow started |
| `POST` | `/api/v1/submissions/pipeline` | Full pipeline — ingest + LangGraph workflow |
| `GET` | `/api/v1/audit/{submission_id}` | Audit trail for a submission |
| `GET` | `/api/v1/queue` | List pending underwriter queue items (paginated) |
| `GET` | `/api/v1/queue/{queue_id}` | Full queue item with submission and risk details |
| `POST` | `/api/v1/queue/{queue_id}/decision` | Submit underwriter decision — resumes pipeline |

### Pipeline Request

```json
{
  "submission_ref": "SUB-2024-001",
  "class_of_business": "commercial_property",
  "jurisdiction": "NZ",
  "document_content": "...broker submission text..."
}
```

### Pipeline Response

```json
{
  "submission_id": "uuid",
  "workflow_status": "COMPLETED | AWAITING_HUMAN | DECLINED",
  "claim_profile": { "..." },
  "hazard_score": { "..." },
  "risk_assessment": {
    "decision": "ACCEPT",
    "risk_score": 0.42,
    "confidence_score": 0.87
  },
  "underwriter_decision": { "..." },
  "pricing_output": {
    "annual_premium": 6840.00,
    "currency": "NZD"
  },
  "governance_decision": {
    "governance_outcome": "APPROVED",
    "checks_passed": ["..."]
  }
}
```

---

## Tech Stack

### AI / LLM Layer

| Component | Technology | Version |
|-----------|-----------|---------|
| LLM Provider | Anthropic Claude API | `anthropic >= 0.40.0` |
| LLM Models | Claude Haiku 4.5, Claude Sonnet 4.6 | — |
| Workflow Orchestration | LangGraph StateGraph | `langgraph >= 0.2.0` |
| LangGraph Checkpointing | PostgresSaver (sync psycopg3) | built into `langgraph` |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 | `sentence-transformers >= 3.0.0` |
| Vector Database | pgvector (PostgreSQL extension) | `pgvector >= 0.3.0` |

### Backend

| Component | Technology | Version |
|-----------|-----------|---------|
| API Framework | FastAPI | `>= 0.115.0` |
| ASGI Server | Uvicorn | `>= 0.32.0` |
| Data Validation | Pydantic v2 | `>= 2.10.0` |
| Settings | pydantic-settings | `>= 2.6.0` |
| Async ORM | SQLAlchemy 2.0 (async) | `>= 2.0.0` |
| DB Driver | asyncpg | `>= 0.30.0` |
| Migrations | Alembic | `>= 1.14.0` |
| Sync PG Driver | psycopg3 | `>= 3.3.4` |

### Infrastructure

| Component | Technology |
|-----------|-----------|
| Database | PostgreSQL 17 + pgvector extension |
| Containerisation | Docker Compose |

### Frontend / UI

| Component | Technology |
|-----------|-----------|
| Underwriter UI | Streamlit (`>= 1.40.0`) |
| Cost Dashboard | Streamlit (page within the Underwriter UI) |

### Developer Tooling

| Tool | Purpose |
|------|---------|
| `uv` | Fast Python package manager and virtualenv |
| `ruff` | Linting and formatting |
| `mypy` | Static type checking |
| `pytest` + `pytest-asyncio` | Async test suite |
| `pytest-cov` | Coverage reporting |
| `pre-commit` | Git hook enforcement |

---

## Running Locally

### Prerequisites

- Docker Desktop running
- Python 3.12+
- `uv` installed (`pip install uv`)
- Anthropic API key

### Setup

```bash
# 1. Clone and enter the project
git clone https://github.com/rajkumar611/AI_UNDERWRITING_SYSTEMS.git
cd AI_UNDERWRITING_SYSTEMS

# 2. Create .env from example
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env

# 3. Start PostgreSQL
docker compose up postgres -d

# 4. Install dependencies
uv sync

# 5. Run database migrations (creates all tables + pgvector extension)
uv run alembic upgrade head

# 6. Seed benchmark data (15 customers, 15 claims, 15 embeddings, 8 regulations)
uv run python scripts/seed_data.py

# 7. Start the API server (port 8081)
uv run uvicorn main:app --port 8081 --reload

# 8. Start the Underwriter UI (separate terminal)
uv run streamlit run streamlit_app.py --server.port 8502

# The Cost Dashboard is built into the Underwriter UI — no separate command needed.
# Access it via the "LLM Cost Dashboard" page in the sidebar.
```

### Access Points

| Service | URL |
|---------|-----|
| API docs (Swagger) | http://localhost:8081/docs |
| Underwriter UI | http://localhost:8502 |
| Cost Dashboard | http://localhost:8502 (sidebar page within Underwriter UI) |

---

## Testing

```bash
# Run full test suite
uv run pytest

# With coverage
uv run pytest --cov=src --cov-report=html

# Specific modules
uv run pytest tests/api/
uv run pytest tests/pipeline/
uv run pytest tests/platform/
```

### Test Coverage

| Module | What's Tested |
|--------|--------------|
| `tests/api/` | Health check, submission CRUD, pipeline endpoint, queue endpoints |
| `tests/pipeline/` | Document ingestion (happy path, retry, injection), claims (customer match, RAG fallback), hazard (deterministic overrides), risk (all pre-screen rules, scoring formula), pricing (premium calculation, discounts), governance (all outcomes) |
| `tests/platform/` | Database migrations, ORM operations, LLM client model routing, workflow state transitions, checkpoint interrupt/resume, cost recording |

---

## Sample Documents

Seven broker documents in `samples/documents/` exercise each pipeline path:

| File | Scenario | Expected Outcome |
|------|----------|-----------------|
| `clean_auto_approve.txt` | Commercial property, Hamilton CBD, NZD 4.2M, good security, 1 minor prior claim | `ACCEPT` · confidence >= 0.70 · auto-approve path |
| `decline_prompt_injection.txt` | Contains "IGNORE ALL PREVIOUS INSTRUCTIONS", "unrestricted mode", "[SYSTEM OVERRIDE]" | `DECLINED` · `decline_reason=PROMPT_INJECTION` · no LLM called |
| `decline_missing_fields.txt` | Missing `sum_insured`, `year_built`, `gross_floor_area_sqm` | `DECLINED` · mandatory field validation failure |
| `referral_hazard_zone.txt` | Hawke's Bay flood zone, near Tutaekuri River, post-Cyclone Gabrielle risk, 1 flood claim NZD 55k | `REFER` · HIGH flood hazard reduces confidence · human review queue |
| `referral_large_claim.txt` | Single large historical claim exceeding NZD 200k threshold | `REFER` · large loss loading triggers confidence penalty |
| `referral_more_claims.txt` | Multiple claims in 3-year window pushing risk score above auto-approve threshold | `REFER` · claims frequency drives human escalation |
| `referral_sum_insured.txt` | Sum insured exceeds NZD/AUD 50,000,000 pre-screen threshold | `REFER` · deterministic pre-screen rule fires · `pre_screen_triggered=True` |

---

## Project Structure

```
AI_UNDERWRITING_SYSTEMS/
├── main.py                                    FastAPI entry point + router wiring
├── streamlit_app.py                           Underwriter UI (Submit · Queue · Lookup)
├── pyproject.toml                             Dependencies managed by uv
├── docker-compose.yml                         PostgreSQL 17 + pgvector
├── Dockerfile
├── .env / .env.example
│
├── src/underwriting/
│   ├── pipeline/
│   │   ├── document_ingestion_agent/
│   │   │   ├── agent.py                       Claude Haiku extraction + injection detection
│   │   │   └── schemas.py                     SubmissionData (24 fields)
│   │   ├── claims_history_agent/
│   │   │   ├── agent.py                       3-tier customer match + pgvector RAG
│   │   │   └── schemas.py                     ClaimsProfile, ClaimsStats
│   │   ├── hazard_evaluation_agent/
│   │   │   ├── agent.py                       NZ/AU geo lookup + deterministic scoring
│   │   │   └── schemas.py                     HazardScore, HazardLevel
│   │   ├── underwriting_risk_agent/
│   │   │   ├── agent.py                       Pre-screen rules + Claude Sonnet synthesis
│   │   │   └── schemas.py                     RiskAssessment
│   │   ├── human_in_the_loop/
│   │   │   ├── agent.py                       Queue enqueue, SLA, decision recording
│   │   │   └── schemas.py                     UnderwriterQueueItem, UnderwriterDecision
│   │   └── pricing_agent/
│   │       ├── agent.py                       Python premium calc + Haiku rationale
│   │       └── schemas.py                     PricingOutput
│   │
│   └── platform/
│       ├── database/
│       │   ├── models.py                      All ORM models incl. Vector(384) + HNSW
│       │   └── connection.py                  Async session factory
│       ├── orchestration/
│       │   ├── workflow.py                    LangGraph StateGraph + checkpoint + HITL
│       │   └── prompt_registry.py             Versioned prompts, lru_cache, {{VAR}} render
│       ├── governance_agent/
│       │   ├── agent.py                       Final compliance gate — Sonnet 4096 tokens
│       │   └── schemas.py                     GovernanceDecision
│       ├── llm/
│       │   └── client.py                      Shared AsyncAnthropic + model routing table
│       ├── cost_tracking/
│       │   ├── pricing.py                     Token to USD conversion per model
│       │   ├── middleware.py                  Per-call cost recorder
│       │   └── dashboard.py                   Streamlit cost analytics
│       ├── audit/
│       │   └── writer.py                      Hash-chained audit trail writer
│       ├── progress_tracker.py                Real-time pipeline step tracking
│       └── security/                          sanitiser.py (planned)
│
│   └── api/routers/
│       ├── health.py                          GET /health
│       ├── submissions.py                     POST + GET /api/v1/submissions
│       └── pipeline.py                        Pipeline + queue endpoints
│
├── alembic/versions/                          5 migrations (0001-0005)
├── prompts/                                   7 agent prompt files v1.0.md
├── samples/documents/                         7 broker test documents
├── scripts/
│   ├── seed_data.py                           15 customers · 15 claims · 15 embeddings
│   └── run_ingestion.py                       CLI ingestion runner
└── tests/                                     API · pipeline · platform test suites
```

---

## Jurisdiction Support

The system operates under **New Zealand and Australian** regulatory frameworks:

- **NZ:** RBNZ and FMA compliance rules; NZD pricing; NZ geographic hazard tables (Wellington seismic, Hawke's Bay flood)
- **AU:** APRA compliance rules; AUD pricing; AU geographic hazard tables (QLD/NT cyclone, NSW/VIC flood, WA/NSW fire)

Jurisdiction is passed with every submission and propagates through the entire workflow, ensuring the correct regulatory rules are applied at governance.

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Deterministic pre-screening | Rules that can be expressed as boolean logic should never depend on LLM output — eliminates variance and reduces cost by 60-80% on clear-cut cases |
| pgvector over a dedicated vector DB | PostgreSQL already manages policy and claims data; keeping vectors in the same database eliminates a network hop and a consistency boundary |
| MemorySaver replaced by AsyncPostgresSaver | Production HITL requires durable checkpoints that survive server restarts; in-memory checkpoints cannot support cross-request resume |
| Haiku for extraction, Sonnet for reasoning | Extraction is a high-volume, structured task; reasoning about risk requires deeper context — routing by task type reduces per-submission cost by ~50% vs. using Sonnet throughout |
| asyncio.gather for parallel agents | Claims and hazard evaluation are independent read operations; parallelism halves wall-clock time for the most latency-sensitive pipeline stage |
| All numeric calculations in Python | Pricing, risk scoring, and confidence formulas must be reproducible and auditable; LLM arithmetic is non-deterministic, Python arithmetic is exact |
| temperature=0 on all agents | Underwriting decisions must be reproducible; zero temperature ensures the same input always produces the same structured output |

---

*Built by Raj Kumar — Lead Developer, QBE Insurance NZ. 15 years of enterprise experience across Accenture, Infosys, and QBE. Certified in Azure AI (AI-900, AI-102), Claude Fundamentals, and Claude Code.*
