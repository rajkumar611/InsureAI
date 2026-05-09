# AI_UNDERWRITING_SYSTEMS — Claude Code Project Guide

## Project Overview
Enterprise-grade multi-agent AI system for insurance underwriting. Built by Raj (Lead Developer,
QBE Insurance NZ) as a portfolio project targeting senior AI engineering roles in Singapore.

**GitHub:** https://github.com/rajkumar611/AI_UNDERWRITING_SYSTEMS.git
**Root:** C:\Users\QBE\Downloads\GitHub Repos\AI_UNDERWRTING_SYSTEM
**Local folder:** C:\Users\QBE\Downloads\GitHub Repos\AI_UNDERWRTING_SYSTEM

## About the Developer
- **Raj** — 15+ years IT experience, Lead Developer at QBE Insurance NZ since 2018
- Prior: Accenture (8 yrs), Infosys (3 yrs)
- Stack: .NET, C#, ASP.NET, SQL Server, Blazor, Web API, Python, Azure
- AI Certs: Azure AI 900, Azure AI 102, Claude Fundamentals, Claude Code
- Prior AI projects: SDLC Agents, Insurance Claims Adjuster (MCP), WhatsApp Agent, RAG Demo,
  LangChain/LangGraph demos

---

## Current Implementation Status — ALL AGENTS COMPLETE

Every agent, the LangGraph workflow, the FastAPI pipeline endpoints, and the Streamlit UI are
fully built and tested end-to-end.

### Pipeline Agents (all in `src/underwriting/pipeline/`)

| Agent | File | Status | Notes |
|---|---|---|---|
| Document Ingestion | `document_ingestion_agent/agent.py` | DONE | Claude Haiku, Pydantic validation, prompt-injection detection |
| Claims History | `claims_history_agent/agent.py` | DONE | RAG via pgvector, customer match → benchmark fallback |
| Hazard Evaluation | `hazard_evaluation_agent/agent.py` | DONE | NZ/AU keyword lookup for seismic/flood/fire zones |
| Underwriting Risk | `underwriting_risk_agent/agent.py` | DONE | Deterministic pre-screen + Claude Sonnet synthesis |
| Human-in-the-Loop | `human_in_the_loop/agent.py` | DONE | Queue enqueue, SLA, decision recording |
| Pricing | `pricing_agent/agent.py` | DONE | Market rate tables, loadings/discounts, Claude Haiku |

### Platform (all in `src/underwriting/platform/`)

| Component | File | Status | Notes |
|---|---|---|---|
| LLM Client | `llm/client.py` | DONE | Shared async Anthropic client + model routing |
| Governance Agent | `governance_agent/agent.py` | DONE | Final gatekeeper — Claude Sonnet, 4096 tokens |
| LangGraph Workflow | `orchestration/workflow.py` | DONE | StateGraph, PostgresSaver (sync) checkpointer, interrupt/resume for HITL |
| Cost Tracking | `cost_tracking/middleware.py` | DONE | Records token cost after every LLM call |
| Cost Dashboard | `cost_tracking/dashboard.py` | DONE | Streamlit finance dashboard |
| Cost Pricing | `cost_tracking/pricing.py` | DONE | Real cost calc from Anthropic token counts |
| Prompt Registry | `orchestration/prompt_registry.py` | DONE | Versioned prompts, `{{VAR}}` rendering, cached |
| Audit Writer | `audit/writer.py` | DONE | Hash-chained append-only decision logger |
| Progress Tracker | `progress_tracker.py` | DONE | Real-time pipeline step tracking |

### API & UI

| File | Status | Notes |
|---|---|---|
| `src/underwriting/api/routers/health.py` | DONE | GET /health |
| `src/underwriting/api/routers/submissions.py` | DONE | POST + GET /api/v1/submissions |
| `src/underwriting/api/routers/pipeline.py` | DONE | Full pipeline + queue endpoints |
| `streamlit_app.py` | DONE | Multi-page UI: Submit Document, Queue, Submission Lookup |
| `main.py` | DONE | FastAPI app wiring all routers |

### Infrastructure

| File | Status |
|---|---|
| `alembic/versions/` | 5 migrations: 0001 initial, 0002 resize vector 1536→384, 0003 customers/policies/claims, 0004 submission extracted_data fields, 0005 queue pipeline_state_snapshot |
| `scripts/seed_data.py` | 15 customers, 15 claims, 15 embeddings, 8 regulations |
| `prompts/*/v1.0.md` | All 7 agent prompts versioned |
| `tests/` | Schema tests, health + submission API tests |
| `samples/documents/*.txt` | 7 broker sample docs (auto-approve, 2 decline, 4 referral scenarios) |

### Still to build (optional enhancements)
- `platform/security/sanitiser.py` — code-level prompt injection filter (currently handled in LLM prompt)

---

## How to Run Locally

```bash
# Prerequisites: Docker Desktop running, Python 3.12+, uv installed

# 1. Start infrastructure
docker compose up postgres -d

# 2. Install dependencies
uv sync

# 3. Run migrations
uv run alembic upgrade head

# 4. Seed the database
uv run python scripts/seed_data.py

# 5. Start the API (port 8081) — use the batch script to avoid Windows event loop issues
start_api.bat
# or: uv run python run.py

# 6. Start the Streamlit UI (separate terminal)
start_streamlit.bat
# or: set VIRTUAL_ENV= && uv run streamlit run streamlit_app.py

# 7. Run tests
uv run pytest

# API docs:      http://localhost:8081/docs
# Streamlit UI:  http://localhost:8502
# Cost dashboard: uv run streamlit run src/underwriting/platform/cost_tracking/dashboard.py
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/health/ready` | Readiness check — DB connectivity |
| POST | `/api/v1/submissions` | Create submission record |
| GET | `/api/v1/submissions/{ref}` | Get submission by policy number or UUID |
| GET | `/api/v1/submissions/{submission_id}/progress` | Real-time pipeline progress |
| POST | `/api/v1/submissions/ingest` | Document ingestion only (no workflow) |
| POST | `/api/v1/submissions/pipeline` | Ingest document + run full pipeline |
| GET | `/api/v1/audit/{submission_id}` | Audit trail for a submission |
| GET | `/api/v1/queue` | List pending underwriter queue items |
| GET | `/api/v1/queue/{queue_id}` | Get queue item with full submission details |
| POST | `/api/v1/queue/{queue_id}/decision` | Submit underwriter decision + resume pipeline |

---

## Key Technical Decisions

### LLM Model Routing (live in `platform/llm/client.py`)
```python
MODEL_FOR_AGENT = {
    "document_ingestion_agent": "claude-haiku-4-5-20251001",
    "claims_history_agent":     "claude-haiku-4-5-20251001",
    "hazard_evaluation_agent":  "claude-sonnet-4-6",
    "underwriting_risk_agent":  "claude-sonnet-4-6",
    "governance_agent":         "claude-sonnet-4-6",
    "pricing_agent":            "claude-haiku-4-5-20251001",
}
```

### LangGraph Workflow (`platform/orchestration/workflow.py`)
- `WorkflowState` TypedDict — all JSON-serializable (no DB sessions in state)
- Nodes: `parallel_analysis` → `underwriting_risk` → routing → `human_review` / `auto_approve` → `pricing` → `governance` / `decline`
- `parallel_analysis_node` runs claims + hazard via `asyncio.gather()`
- `human_review_node` calls `interrupt()` to pause; resumes via `Command(resume=...)` when underwriter submits decision
- **Checkpointer: `PostgresSaver` (sync) + `ConnectionPool` (psycopg_pool sync)** — thread_id == submission_id
  - Uses sync psycopg3 driver to avoid Windows `ProactorEventLoop` incompatibility with async psycopg3
  - LangGraph dispatches sync checkpoint calls via thread pool executor automatically
- Public API: `run_pipeline()` and `resume_pipeline()`

### Embeddings & RAG
- **sentence-transformers `all-MiniLM-L6-v2`** — free, local, 384-dim, loaded once via `@lru_cache`
- pgvector `Vector(384)` with HNSW index in `claims_embeddings` table
- Benchmark SQL excludes `fraud_flag = true` — fraud from other customers must not taint new submissions
- Customer match: ABN/NZBN exact → name ILIKE → vector similarity fallback

### Deterministic Pre-screening (in `underwriting_risk_agent/agent.py`)
Fires before any LLM call:
- `overall_hazard_level == EXTREME` AND `total_claims_3yr > 2` → auto-DECLINE
- `FRAUD_SUSPICION` in risk flags → auto-DECLINE
- `sum_insured > NZD/AUD 50,000,000` → auto-REFER
- `hazard_score.confidence < 0.50` → auto-REFER
- `extraction_confidence == low` → auto-REFER
- `data_quality == LOW` → NOT a pre-screen rule; penalises confidence score (−0.15) and goes to LLM

### Database
- PostgreSQL 17 + pgvector via Docker
- `DATABASE_URL=postgresql+asyncpg://qbe:localdev@localhost:5432/qbe_underwriting`
- Async SQLAlchemy 2.0 with `mapped_column` / `Mapped` syntax
- Each LangGraph node creates its own DB session (not passed through state)

### Jurisdictions
- **NZ** → RBNZ/FMA rules
- **AU** → APRA rules
- No Singapore, no MAS, no SGD (QBE NZ operates in NZ and AU only)

---

## Folder Structure

```
AI_UNDERWRITING_SYSTEMS/
├── main.py                            ← FastAPI entry point
├── run.py                             ← Windows launcher (sets SelectorEventLoop before uvicorn)
├── start_api.bat                      ← Demo launcher: clears VIRTUAL_ENV + starts API
├── start_streamlit.bat                ← Demo launcher: clears VIRTUAL_ENV + starts Streamlit
├── streamlit_app.py                   ← Underwriter UI (Submit, Queue, Lookup)
├── README.md                          ← Comprehensive technical README (generated)
├── pyproject.toml
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── .env / .env.example
│
├── src/
│   └── underwriting/
│       ├── pipeline/
│       │   ├── document_ingestion_agent/   schemas.py ✓  agent.py ✓
│       │   ├── claims_history_agent/       schemas.py ✓  agent.py ✓
│       │   ├── hazard_evaluation_agent/    schemas.py ✓  agent.py ✓
│       │   ├── underwriting_risk_agent/    schemas.py ✓  agent.py ✓
│       │   ├── human_in_the_loop/          schemas.py ✓  agent.py ✓
│       │   └── pricing_agent/             schemas.py ✓  agent.py ✓
│       ├── platform/
│       │   ├── database/              models.py ✓  connection.py ✓
│       │   ├── orchestration/         prompt_registry.py ✓  workflow.py ✓
│       │   ├── governance_agent/      schemas.py ✓  agent.py ✓
│       │   ├── llm/                   client.py ✓  parsing.py ✓
│       │   ├── cost_tracking/         pricing.py ✓  middleware.py ✓  dashboard.py ✓
│       │   ├── audit/                 writer.py ✓  (hash-chained audit trail)
│       │   ├── progress_tracker.py ✓  (real-time pipeline step tracking)
│       │   └── security/              (sanitiser.py not yet built)
│       └── api/
│           └── routers/               health.py ✓  submissions.py ✓  pipeline.py ✓
│
├── alembic/versions/   0001 ✓  0002 ✓  0003 ✓  0004 ✓  0005 ✓
├── scripts/            seed_data.py ✓  run_ingestion.py ✓
├── prompts/            all 7 agents v1.0.md ✓
├── samples/documents/  7 sample broker docs ✓
└── tests/              conftest ✓  api ✓  pipeline ✓  platform ✓
```

---

## The Underwriting Flow

```
BROKER submits documents
  ↓
POST /api/v1/submissions/pipeline
  ↓
document_ingestion_agent      ← Claude Haiku: extract + sanitise + flag anomalies
  ↓
LangGraph workflow starts
  ↓ (parallel via asyncio.gather)
claims_history_agent          ← RAG: customer claims history or benchmark
hazard_evaluation_agent       ← NZ/AU geo/environmental risk scoring
  ↓ (both complete)
underwriting_risk_agent       ← pre-screen rules → Claude Sonnet synthesis → ACCEPT/DECLINE/REFER
  ↓
  ├─ DECLINE → decline_node → workflow_status = DECLINED
  ├─ ACCEPT (confidence ≥ 0.70) → auto_approve_node → pricing → governance
  └─ REFER / low confidence → human_review_node → interrupt() → workflow_status = AWAITING_HUMAN
                                    ↓
                              POST /api/v1/queue/{id}/decision
                                    ↓
                              resume_pipeline() → pricing → governance
                                    ↓
                              workflow_status = COMPLETED / AWAITING_SENIOR_REVIEW

Cross-cutting (every agent):
  cost_tracking     → token cost recorded in cost_ledger after each LLM call
  governance_agent  → final chain validation: consistency + compliance + fraud signals
```

---

## Design Principles
- Broker documents are UNTRUSTED — sanitised at ingestion before reaching any agent
- Claims history and hazard evaluation run in parallel — neither depends on the other
- Pricing only runs AFTER human review — never on an unconfirmed risk assessment
- Pre-screen rules are deterministic Python — not left to the LLM
- No policy is silently issued on a failed or incomplete workflow
- Every decision is auditable — prompt version, inputs, outputs, confidence all logged
- Human escalation is rule-triggered, not LLM-triggered

---

## Import Convention
```python
from underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from underwriting.platform.database.models import Submission, Customer, Claim
from underwriting.platform.database.connection import get_session
from underwriting.platform.orchestration.prompt_registry import PromptRegistry
from underwriting.platform.orchestration.workflow import run_pipeline, resume_pipeline
```

---

## Session Recovery
If session is lost, tell Claude: **"check memory"**
Memory files: `C:\Users\QBE\.claude\projects\c--Users-QBE-Downloads-GitHub-Repos-AI-UNDERWRTING-SYSTEM\memory\`
