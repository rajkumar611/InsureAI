# QBE-AI-Underwriting — Claude Code Project Guide

## Project Overview
Enterprise-grade multi-agent AI system for insurance underwriting. Built by Raj (Lead Developer,
QBE Insurance NZ) as a portfolio project targeting senior AI engineering roles in Singapore.

**GitHub:** https://github.com/rajkumar611/QBE-AI-UNDERWRITING.git
**Root:** C:\Users\QBE\Downloads\QBE-AI-UNDERWRITING

## About the Developer
- **Raj** — 15+ years IT experience, Lead Developer at QBE Insurance NZ since 2018
- Prior: Accenture (8 yrs), Infosys (3 yrs)
- Stack: .NET, C#, ASP.NET, SQL Server, Blazor, Web API, Python, Azure
- AI Certs: Azure AI 900, Azure AI 102, Claude Fundamentals, Claude Code
- Prior AI projects: SDLC Agents, Insurance Claims Adjuster (MCP), WhatsApp Agent, RAG Demo,
  LangChain/LangGraph demos

---

## Current Implementation Status

### DONE — these files have real, working code

| File / Folder | What it contains |
|---|---|
| `src/qbe_underwriting/platform/database/models.py` | 10 SQLAlchemy ORM models: Customer, Submission, Workflow, Policy, Claim, ClaimsEmbedding, AuditEntry, CostEntry, Regulation, UnderwriterQueueItem |
| `src/qbe_underwriting/platform/database/connection.py` | Async SQLAlchemy engine, session factory, `get_session` dependency |
| `src/qbe_underwriting/platform/orchestration/prompt_registry.py` | Loads versioned prompts from `prompts/`, renders `{{VARIABLE}}` placeholders, cached |
| `src/qbe_underwriting/pipeline/*/schemas.py` | Pydantic v2 output schemas for all 6 pipeline agents |
| `src/qbe_underwriting/platform/governance_agent/schemas.py` | `GovernanceDecision` Pydantic schema |
| `src/qbe_underwriting/platform/compliance_agent/schemas.py` | `ComplianceResult` Pydantic schema |
| `src/qbe_underwriting/api/routers/health.py` | GET /health |
| `src/qbe_underwriting/api/routers/submissions.py` | POST /api/v1/submissions, GET /api/v1/submissions/{id} |
| `main.py` | FastAPI app with lifespan, CORS, routers wired up |
| `alembic/versions/` | 3 migrations: 0001 initial schema, 0002 resize vector 1536→384, 0003 customers/policies/claims |
| `scripts/seed_data.py` | Seeds 15 customers, 15 claims, 15 embeddings, 8 regulations using sentence-transformers |
| `prompts/*/v1.0.md` | Versioned system prompts for all 7 agents (document_ingestion, claims_history, hazard_evaluation, underwriting_risk, pricing, governance, compliance) |
| `tests/conftest.py` | pytest fixtures: test DB, session, async HTTP client |
| `tests/pipeline/test_schemas.py` | Pydantic schema validation tests (no DB, no LLM) |
| `tests/platform/test_schemas.py` | Governance + compliance schema tests |
| `tests/api/test_health.py` | Health endpoint test |
| `tests/api/test_submissions.py` | Submission create + get tests |

### DONE TODAY — new files with real working code

| File | What it does |
|---|---|
| `src/qbe_underwriting/platform/llm/client.py` | Shared async Anthropic client + `MODEL_FOR_AGENT` routing dict |
| `src/qbe_underwriting/platform/cost_tracking/pricing.py` | Real cost calc from Anthropic token counts |
| `src/qbe_underwriting/platform/cost_tracking/middleware.py` | Writes cost to `cost_ledger` table after every LLM call |
| `src/qbe_underwriting/platform/cost_tracking/dashboard.py` | Streamlit cost dashboard for finance team |
| `src/qbe_underwriting/pipeline/document_ingestion_agent/agent.py` | **First working agent** — calls Claude Haiku, validates with Pydantic |
| `samples/documents/*.txt` | 4 sample broker documents (happy path, high risk, missing fields, prompt injection) |
| `scripts/run_ingestion.py` | Developer test script — run any sample through the agent |

### BUGS FIXED TODAY
- `PromptRegistry` PROMPTS_ROOT was `parents[2]` → fixed to `parents[4]` (project root)
- Claude wraps JSON in ```json fences despite prompt — fixed with `_strip_markdown_fences()` in agent
- `security_features: null` from LLM failed Pydantic — fixed with `NullableList = Annotated[list[str], BeforeValidator(lambda v: v or [])]`

### TEST RESULTS — all 4 samples passing
| Sample | Confidence | Result |
|---|---|---|
| `harbour_fresh` | high | All fields extracted correctly |
| `high_risk` | high | Flood zone + 4 claims extracted correctly |
| `missing_fields` | medium | 12 missing fields identified, 3 anomalies flagged |
| `prompt_injection` | high | Both injection attempts flagged in anomalies, not executed |

### EMPTY SCAFFOLDING — still to build

| Folder | What needs to be built |
|---|---|
| `src/qbe_underwriting/pipeline/claims_history_agent/` | `agent.py` — RAG over claims DB using pgvector |
| `src/qbe_underwriting/pipeline/hazard_evaluation_agent/` | `agent.py` — property/environmental risk scoring |
| `src/qbe_underwriting/pipeline/underwriting_risk_agent/` | `agent.py` — synthesise all inputs → Accept/Decline/Refer |
| `src/qbe_underwriting/pipeline/human_in_the_loop/` | `agent.py` — underwriter review queue |
| `src/qbe_underwriting/pipeline/pricing_agent/` | `agent.py` — premium calculation |
| `src/qbe_underwriting/platform/security/` | `sanitiser.py` — code-level prompt injection filter |
| `src/qbe_underwriting/platform/observability/` | `audit_writer.py` — append-only decision logger |
| `src/qbe_underwriting/platform/orchestration/` | `workflow.py` — LangGraph state machine |

### NEXT TASK — two options, discuss with Raj
**Option A:** Build `claims_history_agent/agent.py` — RAG query over seeded claims data
**Option B:** Wire up FastAPI submission endpoint to trigger the pipeline — gives a proper HTTP entry point

---

## Key Technical Decisions Made

### Embeddings
- **sentence-transformers `all-MiniLM-L6-v2`** — free, local, no API key, 384-dim vectors
- pgvector stores Vector(384) with HNSW index in `claims_embeddings` table
- This IS the RAG vector store — not Pinecone, not a separate service

### LLM Model Routing (designed, not yet coded)
Each agent uses a different model based on task complexity:
```python
MODEL_ROUTING = {
    "document_ingestion_agent": "claude-haiku-4-5-20251001",   # extraction only
    "claims_history_agent":     "claude-haiku-4-5-20251001",   # retrieval + summarise
    "hazard_evaluation_agent":  "claude-sonnet-4-6",            # moderate reasoning
    "underwriting_risk_agent":  "claude-sonnet-4-6",            # deep synthesis
    "governance_agent":         "claude-sonnet-4-6",            # high-stakes validation
    "pricing_agent":            "claude-haiku-4-5-20251001",    # mostly deterministic
}
```
This config goes into `platform/orchestration/` when the first agent is built.

### Database
- PostgreSQL 17 + pgvector via Docker
- `DATABASE_URL=postgresql+asyncpg://qbe:localdev@localhost:5432/qbe_underwriting`
- Async SQLAlchemy 2.0 with `mapped_column` / `Mapped` syntax
- 10 ORM models: 4 seeded at startup, 6 transactional (populated when pipeline runs)

### Jurisdictions
- **NZ only** → RBNZ/FMA rules
- **AU only** → APRA rules
- No Singapore, no MAS, no SGD anywhere in this project
  (Raj's career goal is Singapore but QBE NZ operates in NZ and AU only)

### Pre-screening (deterministic rules before LLM)
In `underwriting_risk_agent` — checked before any LLM call:
- `HazardScore.flood_zone == "EXTREME"` AND claims > 2 → auto-Refer
- `sum_insured > $50M` → always Refer
- `ClaimProfile.risk_flags` contains `"FRAUD_SUSPICION"` → auto-Decline

---

## How to Run Locally

```bash
# Prerequisites: Docker Desktop running, Python 3.12+, uv installed

# 1. Start infrastructure
docker compose up postgres redis -d

# 2. Install dependencies
uv sync

# 3. Run migrations
uv run alembic upgrade head

# 4. Seed the database
uv run python scripts/seed_data.py

# 5. Start the API
uv run uvicorn main:app --reload

# 6. Run tests
uv run pytest

# API docs: http://localhost:8000/docs
```

---

## Folder Structure

```
QBE-AI-UNDERWRITING/
├── main.py                            ← FastAPI entry point (uvicorn main:app)
├── pyproject.toml                     ← all deps + tooling (pytest, ruff, mypy)
├── alembic.ini                        ← script_location=alembic, prepend_sys_path=src
├── docker-compose.yml                 ← Postgres + Redis for local dev
├── Dockerfile                         ← production container, PYTHONPATH=/app/src
├── .pre-commit-config.yaml            ← ruff lint/format + file hygiene hooks
├── .env / .env.example                ← secrets (never committed)
│
├── src/
│   └── qbe_underwriting/             ← single top-level package (src layout)
│       ├── pipeline/
│       │   ├── document_ingestion_agent/   schemas.py ✓  agent.py ✗
│       │   ├── claims_history_agent/       schemas.py ✓  agent.py ✗
│       │   ├── hazard_evaluation_agent/    schemas.py ✓  agent.py ✗
│       │   ├── underwriting_risk_agent/    schemas.py ✓  agent.py ✗
│       │   ├── human_in_the_loop/          schemas.py ✓  agent.py ✗
│       │   └── pricing_agent/              schemas.py ✓  agent.py ✗
│       ├── platform/
│       │   ├── database/              models.py ✓  connection.py ✓
│       │   ├── orchestration/         prompt_registry.py ✓  workflow.py ✗
│       │   ├── governance_agent/      schemas.py ✓  agent.py ✗
│       │   ├── compliance_agent/      schemas.py ✓  agent.py ✗
│       │   ├── security/              sanitiser.py ✗
│       │   ├── cost_tracking/         middleware.py ✗
│       │   └── observability/         audit_writer.py ✗
│       └── api/
│           └── routers/               health.py ✓  submissions.py ✓
│
├── alembic/
│   ├── env.py
│   └── versions/   0001_initial ✓  0002_resize_vector ✓  0003_customers_policies_claims ✓
│
├── scripts/
│   └── seed_data.py   ← 15 customers, 15 claims, 15 embeddings, 8 regulations
│
├── prompts/
│   ├── document_ingestion_agent/v1.0.md ✓
│   ├── claims_history_agent/v1.0.md     ✓
│   ├── hazard_evaluation_agent/v1.0.md  ✓
│   ├── underwriting_risk_agent/v1.0.md  ✓
│   ├── pricing_agent/v1.0.md            ✓
│   ├── governance_agent/v1.0.md         ✓
│   └── compliance_agent/v1.0.md         ✓
│
├── tests/
│   ├── conftest.py              ← test DB, session, HTTP client fixtures
│   ├── api/                     test_health.py ✓  test_submissions.py ✓
│   ├── pipeline/                test_schemas.py ✓
│   └── platform/                test_schemas.py ✓
│
└── docs/
    ├── architecture/end-to-end-flow.md
    └── Q&A/   01-general through 14-observability (interview prep)
```

---

## The Real Underwriting Flow

```
BROKER submits documents (PDFs, photos, forms)
  ↓
pipeline/document_ingestion_agent    ← OCR + extract + sanitise (prompt injection check)
  ↓                                    ↑ loopback: broker queried for missing docs
platform/orchestration               ← LangGraph state machine takes control
  ↓ (runs in parallel)
pipeline/claims_history_agent        ← RAG: past claims for this customer/property
pipeline/hazard_evaluation_agent     ← flood, fire, structural, environmental risk
  ↓ (both complete)
pipeline/underwriting_risk_agent     ← synthesise → Accept / Decline / Refer + confidence
  ↓
pipeline/human_in_the_loop           ← mandatory for Refer or confidence < 0.70
  ↓
pipeline/pricing_agent               ← premium + terms (only after human sign-off)
  ↓
platform/governance_agent            ← final consistency + compliance validation
  ↓
POLICY ISSUED

Cross-cutting (wrap every agent):
  platform/security          → prompt injection filter
  platform/cost_tracking     → token metering per agent/policy
  platform/observability     → audit trail, OpenTelemetry traces
  platform/compliance_agent  → APRA (AU) + RBNZ/FMA (NZ) rules
```

---

## Design Principles
- Broker documents are UNTRUSTED — sanitised at ingestion before reaching any agent
- Claims history and hazard evaluation run in parallel — neither depends on the other
- Pricing only runs AFTER human review — never on unconfirmed risk assessment
- Conflict resolution is deterministic and rule-based — never left to the LLM
- No policy is silently issued on a failed or incomplete workflow
- Every decision is auditable — prompt version, inputs, outputs, confidence all logged
- Human escalation is rule-triggered, not LLM-triggered

---

## Import Convention
```python
from qbe_underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from qbe_underwriting.platform.database.models import Submission, Customer, Claim
from qbe_underwriting.platform.database.connection import get_session
from qbe_underwriting.platform.orchestration.prompt_registry import PromptRegistry
```

---

## Session Recovery
If session is lost, tell Claude: **"check memory"**
Memory files: `C:\Users\QBE\.claude\projects\c--Users-QBE-Downloads-qbe-ai-underwriting\memory\`
