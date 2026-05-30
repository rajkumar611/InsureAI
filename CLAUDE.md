# INSUREAI — Claude Code Project Guide

**Enterprise multi-agent AI insurance underwriting platform.**  
Built by Raj Kumar (Lead Developer, QBE Insurance NZ) as a portfolio project targeting senior AI engineering roles in Singapore.

---

## 📌 Quick Navigation

- **[Getting Started](#getting-started)** — Run locally in 5 minutes
- **[Project Status](#project-status)** — What's complete
- **[Architecture](#architecture)** — How it works
- **[File Organization](#file-organization)** — Where to find things
- **[Key Workflows](#key-workflows)** — End-to-end flows
- **[Development](#development)** — How to extend
- **[Deployment](#deployment)** — Production checklist

---

## 🚀 Getting Started

### Prerequisites
```bash
# Check versions
python --version              # Python 3.12+
docker --version              # Docker Desktop running
uv --version                  # uv package manager
echo $ANTHROPIC_API_KEY       # Must be set
```

### 5-Minute Setup

```bash
# 1. Clone + enter directory
cd c:\Users\QBE\Downloads\GitHub Repos\INSUREAI

# 2. Start PostgreSQL
docker compose up postgres -d

# 3. Install + migrate
uv sync
uv run alembic upgrade head

# 4. Seed sample data (optional)
uv run python backend/scripts/admin/seed_data.py
uv run python backend/scripts/admin/seed_brokers.py

# 5. Terminal 1: Start API
cd backend && uv run python run.py

# 6. Terminal 2: Start Streamlit UI
cd frontend && uv run streamlit run underwriter_portal.py

# 7. Terminal 3: Run tests
uv run pytest backend/tests -v
```

**Live URLs:**
- API: http://localhost:8081 (Swagger docs: /docs)
- Underwriter Portal: http://localhost:8501
- Cost Dashboard: Sidebar → "LLM Cost Dashboard"

---

## ✅ Project Status

### ✓ Complete (Production Ready)

| Component | Status | Notes |
|---|---|---|
| **6 Pipeline Agents** | ✅ DONE | Document ingestion, claims history, hazard eval, risk scoring, human queue, pricing |
| **2 LLM Models** | ✅ DONE | Claude Haiku (ingest, claims, pricing) + Claude Sonnet (hazard, risk, governance) |
| **LangGraph Workflow** | ✅ DONE | StateGraph + PostgreSQL checkpointer (interrupt/resume for HITL) |
| **FastAPI Backend** | ✅ DONE | 10 endpoints (health, submissions, pipeline, queue, audit) |
| **Broker Authentication** | ✅ DONE | SHA256 API key hashing, rate limiting (10/day), broker status validation |
| **Streamlit UIs** | ✅ DONE | Underwriter portal (submit, queue, lookup) + cost dashboard |
| **Cost Tracking** | ✅ DONE | Real token counts logged, cost_ledger table, USD calculations |
| **Database** | ✅ DONE | 8 migrations, customers, claims, brokers, queue, cost ledger, embeddings |
| **RAG + Embeddings** | ✅ DONE | pgvector HNSW index, 3-tier customer match, benchmark fallback |
| **Audit Trail** | ✅ DONE | Via submission history + cost_ledger + LangGraph checkpoints |
| **Tests** | ✅ DONE | API tests, pipeline tests, workflow routing tests, E2E tests |
| **Docker Deployment** | ✅ DONE | Dockerfile, docker-compose.yml, start scripts (Windows + POSIX) |

### 🔄 Optional (Nice-to-Have)

| Feature | Status | Notes |
|---|---|---|
| **Underwriter Users (Azure AD)** | ⏸️ | NO User/Underwriter table yet; `assigned_underwriter_id` is just VARCHAR. Need: user table + Azure AD bearer token validation + RBAC |
| **Prompt Injection Detector** | ⏸️ | Currently handled in LLM prompts; Python-level filter in `platform/security/sanitiser.py` not implemented |
| **Redis Rate Limiter** | ⏸️ | Using in-memory store; Redis for distributed deployment |
| **Webhook Notifications** | ⏸️ | POST to broker webhooks on submission completion |
| **React Frontend** | ⏸️ | Next.js SPA for brokers; Streamlit sufficient for MVP |

---

## 🏗️ Architecture

### High-Level Flow

```
POST /api/v1/submissions/pipeline
        ↓
        ├─ [1] Document Ingestion (Haiku)
        │       └─ Extract + validate + sanitise
        ↓
        ├─ [2] Parallel Analysis
        │       ├─ Claims History (Haiku) — RAG search
        │       └─ Hazard Evaluation (Sonnet) — Geo scoring
        ↓
        ├─ [3] Underwriting Risk (Sonnet)
        │       ├─ Pre-screen rules (deterministic)
        │       └─ LLM synthesis → ACCEPT / REFER / DECLINE
        ↓
        ├─ [4] Human Escalation (if REFER)
        │       └─ Enqueue + interrupt workflow
        │       └─ Wait for POST /api/v1/queue/{id}/decision
        ↓
        ├─ [5] Pricing (Haiku)
        │       └─ Market rates + loadings/discounts
        ↓
        ├─ [6] Governance (Sonnet)
        │       └─ Final validation + compliance
        ↓
        └─ Submission complete → Cost recorded
```

### Key Design Decisions

1. **Async-First:** All I/O is async (FastAPI, asyncpg, LangGraph)
   - Windows event loop fixed via `backend/run.py` (SelectorEventLoop policy)
   - Never run `uvicorn main:app` directly on Windows — use `run.py` or batch file

2. **Deterministic Pre-Screen:** High-confidence decisions before LLM
   - Avoids "death by a thousand questions" on obviously declining cases
   - Rules: hazard+claims combination → DECLINE, high sum insured → REFER, etc.

3. **Parallel Execution:** Claims + Hazard run simultaneously
   - Independent analysis → no ordering constraints
   - `asyncio.gather()` inside parallel node

4. **PostgreSQL Checkpointing:** LangGraph state persisted after each step
   - Workflow can be resumed if interrupted (human review)
   - No in-memory queue; survives API restarts
   - Async psycopg3 driver (not sync)

5. **Cost Transparency:** Every token counted, every LLM call logged
   - Real Anthropic token counts from `response.usage`
   - USD cost calculated + recorded immediately
   - Cost ledger queryable for audit + finance

6. **Broker API Keys:** SHA256 hashing (not plaintext)
   - Hash stored in DB; plaintext never logged
   - Rate limit per broker (10/day default)
   - Broker status validation (ACTIVE only)

---

## 📁 File Organization

### Root Level

```
INSUREAI/
├── README.md                          ← User-facing quickstart (go here first)
├── CLAUDE.md                          ← This file (developer guide)
├── pyproject.toml                     ← Dependencies + pytest config
├── .env / .env.example                ← Environment variables
├── .pre-commit-config.yaml            ← Linting hooks (ruff, mypy)
├── pyproject.toml                     ← Build config
└── uv.lock                            ← Locked dependency versions
```

### frontend/ — Streamlit UIs

```
frontend/
├── underwriter_portal.py              ← Main UI (Streamlit)
│                                         Pages:
│                                         • Submit Document
│                                         • View Queue (HITL escalations)
│                                         • Submission Lookup
│                                         • LLM Cost Dashboard
├── cost_dashboard.py                  ← Cost analytics (embedded in portal)
├── start_streamlit.bat                ← Batch launcher (Windows)
└── tests/                             ← UI integration tests (if any)
```

### backend/ — FastAPI + Agents

```
backend/
├── main.py                            ← FastAPI app
├── run.py                             ← Windows launcher (event loop fix)
├── alembic.ini                        ← Migration config
├── alembic/versions/                  ← 8 migrations (0001-0008)
│
├── src/underwriting/
│   ├── api/
│   │   ├── middleware/
│   │   │   ├── auth.py               ← X-API-Key validation (SHA256)
│   │   │   ├── rate_limiter.py       ← 10/day per broker
│   │   │   └── logging.py            ← JSON request/response logging
│   │   └── routers/
│   │       ├── health.py             ← /health, /health/ready
│   │       ├── submissions.py        ← /api/v1/submissions/* (CRUD)
│   │       └── pipeline.py           ← /api/v1/submissions/pipeline, /queue/*
│   │
│   ├── database/
│   │   ├── models.py                 ← ORM models (Submission, Broker, etc.)
│   │   │                                Key tables:
│   │   │                                • submissions — master case record
│   │   │                                • customers — ABN/NZBN indexed
│   │   │                                • claims — historical claims
│   │   │                                • brokers — API consumers
│   │   │                                • api_keys — hashed keys
│   │   │                                • underwriter_queue — HITL escalations
│   │   │                                • cost_ledger — token costs
│   │   └── connection.py             ← Async session + pool
│   │
│   ├── pipeline_agents/
│   │   ├── document_ingestion_agent/  ← [1] Extract + validate
│   │   │   ├── agent.py              ← Main logic
│   │   │   └── schemas.py            ← SubmissionData (24 fields)
│   │   │
│   │   ├── claims_history_agent/     ← [2a] RAG search
│   │   │   ├── agent.py              ← 3-tier customer match
│   │   │   └── schemas.py            ← ClaimsProfile, ClaimsStats
│   │   │
│   │   ├── hazard_evaluation_agent/  ← [2b] Geo-spatial risk
│   │   │   ├── agent.py              ← NZ/AU keyword lookup
│   │   │   └── schemas.py            ← HazardScore (level, confidence)
│   │   │
│   │   ├── underwriting_risk_agent/  ← [3] Pre-screen + synthesis
│   │   │   ├── agent.py              ← Deterministic rules + Sonnet
│   │   │   └── schemas.py            ← RiskDecision (action, confidence)
│   │   │
│   │   ├── human_in_the_loop/        ← [4] Queue + interrupt/resume
│   │   │   ├── agent.py              ← Enqueue + workflow pause
│   │   │   └── schemas.py            ← UnderwriterQueue, Decision
│   │   │
│   │   └── pricing_agent/            ← [5] Market rates
│   │       ├── agent.py              ← Apply loadings/discounts
│   │       └── schemas.py            ← PricingQuote
│   │
│   └── platform/
│       ├── llm/
│       │   ├── client.py             ← Shared Anthropic client
│       │   │                            • Model routing (env var overrides)
│       │   │                            • Token counting
│       │   └── parsing.py            ← JSON extraction utilities
│       │
│       ├── orchestration/
│       │   ├── workflow.py           ← LangGraph StateGraph
│       │   │                            • Node definitions
│       │   │                            • Edge routing logic
│       │   │                            • PostgreSQL checkpointer
│       │   └── prompt_registry.py    ← Versioned prompts
│       │                                • {{VAR}} templating
│       │                                • Version lookup
│       │
│       ├── governance_agent/         ← [6] Final validation
│       │   ├── agent.py              ← Compliance + signing
│       │   └── schemas.py
│       │
│       ├── cost_tracking/
│       │   ├── middleware.py         ← Record costs after each LLM call
│       │   └── pricing.py            ← Calculate USD from tokens
│       │
│       └── progress_tracker.py       ← Real-time pipeline progress (no Redis)
```

### database/ — ORM Models & Setup Scripts

```
database/
├── connection.py                      ← Async session + PostgreSQL pool
├── models.py                          ← SQLAlchemy ORM models
├── init_schema.py                     ← Schema initialization utilities
└── admin/
    ├── init_db.py                     ← Initialize database (tables + indexes)
    ├── health_check_db.py             ← Database health check
    ├── seed_data.py                   ← Load 15 customers + 120 claims
    ├── seed_brokers.py                ← Create test broker accounts + API keys
    └── schema_reference.sql           ← Raw SQL schema (reference)
```

### tests/ — Automated & Manual Tests

```
tests/
├── conftest.py                        ← Pytest fixtures + setup
├── api/
│   ├── test_health.py                ← Health check tests
│   ├── test_submissions.py           ← Submission CRUD tests
│   ├── test_pipeline.py              ← Pipeline endpoint tests
│   └── test_e2e_pipeline.py          ← Full workflow E2E
├── pipeline/
│   ├── test_pricing.py               ← Pricing agent logic
│   └── test_schemas.py               ← Schema validation
├── platform/
│   ├── test_workflow_routing.py      ← Workflow branch logic
│   └── test_schemas.py               ← Platform schema tests
└── dev/
    ├── run_ingestion.py              ← Test ingestion agent standalone
    └── test_broker_api.py            ← Test API auth + rate limiting
```

### deployment/ — Docker & Infrastructure

```
deployment/
├── Dockerfile                         ← Container image (Python 3.12 + uv)
├── docker-compose.yml                 ← PostgreSQL + API + Streamlit
└── (batch files in root)
    ├── start_api.bat                  ← Windows API launcher
    └── start_streamlit.bat            ← Windows Streamlit launcher
```

### system_prompts_config/ — Agent Prompts

```
system_prompts_config/
└── agent_prompts/
    ├── document_ingestion_agent/v1.0.md
    ├── claims_history_agent/v1.0.md
    ├── hazard_evaluation_agent/v1.0.md
    ├── underwriting_risk_agent/v1.0.md
    ├── pricing_agent/v1.0.md
    ├── governance_agent/v1.0.md
    └── README.md                      ← How to version + update prompts
```

### sample_broker_files/ — Test Data

```
sample_broker_files/
├── documents/                         ← 7 test scenarios
│   ├── clean_auto_approve.txt        ← Should → ACCEPT
│   ├── decline_missing_fields.txt    ← Should → DECLINE
│   ├── decline_prompt_injection.txt  ← Should → DECLINE
│   ├── referral_hazard_zone.txt      ← Should → REFER
│   ├── referral_large_claim.txt      ← Should → REFER
│   ├── referral_more_claims.txt      ← Should → REFER
│   └── referral_sum_insured.txt      ← Should → REFER
└── README.md                          ← Scenario explanations
```

### evals/ — Performance Benchmarks

```
evals/
├── run_evals.py                       ← Benchmark script
└── scenarios.py                       ← Test scenarios + expected outcomes
```

---

## 🔑 Key Workflows

### Workflow 1: Submit Document & Get Auto-Decision

```bash
# Example: Property insurance, NZ, auto-approve scenario

curl -X POST http://localhost:8081/api/v1/submissions/pipeline \
  -H "X-API-Key: broker-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "submission_ref": "POL-2025-001",
    "class_of_business": "property",
    "jurisdiction": "NZ",
    "document_content": "Insurance application for residential property..."
  }'

# Response (202 Accepted):
{
  "submission_id": "uuid-here",
  "submission_ref": "POL-2025-001",
  "status": "PROCESSING",
  "message": "Pipeline started"
}

# Poll for completion:
curl http://localhost:8081/api/v1/submissions/POL-2025-001 \
  -H "X-API-Key: broker-key-here"

# Response when COMPLETED:
{
  "submission_id": "uuid",
  "status": "COMPLETED",
  "workflow_status": "ACCEPTED",
  "risk_score": 0.72,
  "pricing_quote": {
    "premium": 850.00,
    "loadings": [...],
    "discounts": [...]
  }
}
```

### Workflow 2: Submit Document & Human Escalation

```bash
# Submit document that triggers REFER

curl -X POST http://localhost:8081/api/v1/submissions/pipeline \
  -H "X-API-Key: broker-key-here" \
  -d '{"submission_ref": "POL-2025-002", ...}'

# Response:
{
  "status": "PROCESSING",
  "submission_id": "uuid-2"
}

# Poll — when ready:
curl http://localhost:8081/api/v1/submissions/uuid-2 \
  -H "X-API-Key: broker-key-here"

# Response when AWAITING_HUMAN:
{
  "status": "AWAITING_HUMAN",
  "workflow_status": "AWAITING_HUMAN",
  "message": "Escalated to underwriter queue"
}

# Underwriter checks queue:
curl http://localhost:8081/api/v1/queue \
  -H "X-API-Key: broker-key-here"

# Response:
{
  "items": [
    {
      "queue_id": "queue-uuid",
      "submission_id": "uuid-2",
      "reason": "Manual review required",
      "enqueued_at": "2025-05-30T10:15:00Z",
      "sla_minutes": 120
    }
  ]
}

# Underwriter makes decision:
curl -X POST http://localhost:8081/api/v1/queue/queue-uuid/decision \
  -H "X-API-Key: broker-key-here" \
  -d '{
    "underwriter_id": "UW-001",
    "action": "ACCEPT",
    "override_risk_score": 0.65,
    "conditions": ["Add flood exclusion"],
    "notes": "Verified with customer — acceptable risk"
  }'

# Pipeline resumes → Pricing + Governance → COMPLETED
```

### Workflow 3: Check Cost Ledger

```bash
# View dashboard at http://localhost:8501/cost_dashboard
# Or query raw:

curl http://localhost:8081/api/v1/submissions/uuid-2/cost \
  -H "X-API-Key: broker-key-here"

# Response:
{
  "total_cost_usd": 0.0342,
  "calls": [
    {
      "agent": "document_ingestion_agent",
      "model": "claude-haiku-4-5-20251001",
      "input_tokens": 1500,
      "output_tokens": 320,
      "cost_usd": 0.0078
    },
    {
      "agent": "underwriting_risk_agent",
      "model": "claude-sonnet-4-6",
      "input_tokens": 3200,
      "output_tokens": 850,
      "cost_usd": 0.0147
    },
    ...
  ]
}
```

---

## 📊 Database Seeding Strategy

### Architecture: Three Seeding Layers

```
database/admin/
├── init_db.py              ← [0] CREATE schema (tables + indexes)
├── seed_data.py            ← [1] LOAD business domain data
├── seed_brokers.py         ← [2] CREATE external partner accounts
└── health_check_db.py      ← Verify database health
```

### Layer 1️⃣: `init_db.py` — Schema Initialization
**What:** Creates all tables, extensions (pgvector), and indexes from `tables_creation.sql`
**When:** First time setup OR fresh database
**Data Impact:** NONE (schema only)
**Command:** `uv run python database/admin/init_db.py`

### Layer 2️⃣: `seed_data.py` — Business Domain Data
**What:** Populates CUSTOMERS, CLAIMS, REGULATIONS, EMBEDDINGS for testing
**Who:** Insurance applicants (external), historical claim records
**Records:** 15 customers, 120+ claims, 50+ regulations
**Use Case:** When broker submits "Pacific Properties", RAG search finds their historical claims
**Command:** `uv run python database/admin/seed_data.py`

```python
# What gets created:
CUSTOMERS (15 records)
├── ID: UUID
├── customer_ref: "CUST-NZ-001"
├── full_name: "James Tane" or "Pacific Properties Limited"
├── abn_nzbn: Tax ID (optional)
├── jurisdiction: "NZ" or "AU"
└── kyc_status: "VERIFIED"

CLAIMS (120+ records, linked to customers)
├── claim_number: "CLM-2023-001"
├── customer_id: (FK to CUSTOMERS)
├── cause_of_loss: "Fire damage", "Water damage", etc.
├── incurred_amount: 50000.00
├── claim_date: TIMESTAMP
└── is_large_loss: BOOLEAN

REGULATIONS (50+ records)
├── jurisdiction: "NZ" or "AU"
├── class_of_business: "property", "motor", etc.
├── rule_code: "NZ-PROP-001"
├── rule_description: Compliance rule text
└── effective_date: TIMESTAMP

CLAIMS_EMBEDDINGS (384-dim vectors for pgvector search)
├── customer_ref, claim_id
├── embedding: vector(384) — for semantic search
└── Used by: claims_history_agent for RAG
```

### Layer 3️⃣: `seed_brokers.py` — External Partner Accounts
**What:** Creates BROKERS and API_KEYS for external API consumers
**Who:** Insurance brokers (external partners submitting documents)
**Records:** 3 demo brokers, 3 API keys
**Use Case:** Broker calls `POST /api/v1/submissions/pipeline` with X-API-Key header
**Command:** `uv run python database/admin/seed_brokers.py`

```python
# What gets created:
BROKERS (3 records)
├── name: "Acme Insurance Brokers"
├── email: "api@acmeinsurance.com"
├── organization: "Acme Inc"
├── status: "ACTIVE"
└── created_at: TIMESTAMP

API_KEYS (1 per broker)
├── broker_id: (FK to BROKERS)
├── api_key_hash: SHA256("sk-broker-001-acme-test-key-2026")
└── created_at: TIMESTAMP

# API key is printed during seeding:
API Key (SAVE THIS): sk-broker-001-acme-test-key-2026
```

### Complete Setup Flow

```bash
# Step 1: Initialize schema (tables + indexes)
uv run python database/admin/init_db.py

# Step 2: Load test customer data + claims history
uv run python database/admin/seed_data.py

# Step 3: Create broker accounts + API keys
uv run python database/admin/seed_brokers.py

# Step 4: Verify database is healthy
uv run python database/admin/health_check_db.py

# Step 5: Start API and test
uv run python backend/run.py
# In another terminal:
uv run python tests/dev/test_broker_api.py
```

### ⚠️ Important: Missing Underwriter Users

**Current Status:** NO User/Underwriter table yet!

**What's Missing for Azure AD Integration:**
```python
# TODO: Create this table (Phase X)
class Underwriter(Base):
    __tablename__ = "underwriters"
    id = Column(UUID, primary_key=True)
    email = Column(String(128), unique=True)  # user@qbe.co.nz
    name = Column(String(128))
    azure_ad_oid = Column(String(255), unique=True)  # From Azure AD token
    role = Column(String(32))  # "SENIOR_UW", "JUNIOR_UW", "MANAGER"
    department = Column(String(64))  # "Property", "Liability", "Motor"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime)

# Currently, UnderwriterQueueItem.assigned_underwriter_id is just VARCHAR
# This needs to be refactored to FK → underwriters.id
```

**Why It Matters:**
1. Underwriter Portal (/login) needs Azure AD bearer token validation
2. Audit trail needs to record WHO made the decision
3. Human escalation queue needs proper user assignment
4. Future: RBAC for department-specific workflows

**Next Steps:** Create seed_underwriters.py + add Underwriter model in Phase X

---

## 🛠️ Development

### Add a New Agent

**Step 1: Create folder + schema**
```bash
mkdir -p backend/src/underwriting/pipeline_agents/my_agent
touch backend/src/underwriting/pipeline_agents/my_agent/{__init__.py,schemas.py,agent.py}
```

**Step 2: Define schemas** (`schemas.py`)
```python
from pydantic import BaseModel

class MyAgentInput(BaseModel):
    submission_id: str
    risk_score: float
    
class MyAgentOutput(BaseModel):
    action: str
    confidence: float
```

**Step 3: Implement agent** (`agent.py`)
```python
from anthropic import Anthropic
from .schemas import MyAgentInput, MyAgentOutput

async def run(input_data: MyAgentInput) -> MyAgentOutput:
    client = Anthropic()
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": "..."}]
    )
    return MyAgentOutput(action="ACCEPT", confidence=0.8)
```

**Step 4: Register in workflow** (`workflow.py`)
```python
def my_agent_node(state: WorkflowState) -> WorkflowState:
    input_data = MyAgentInput(...)
    output = await run(input_data)
    return {**state, "my_agent_output": output}

graph.add_node("my_agent", my_agent_node)
graph.add_edge("previous_node", "my_agent")
```

**Step 5: Register model choice** (`llm/client.py`)
```python
MODEL_FOR_AGENT = {
    "my_agent": os.getenv("MODEL_MY_AGENT", "claude-sonnet-4-6"),
}
```

**Step 6: Write tests** (`backend/tests/pipeline/test_my_agent.py`)
```python
import pytest
from underwriting.pipeline_agents.my_agent.agent import run
from underwriting.pipeline_agents.my_agent.schemas import MyAgentInput

@pytest.mark.asyncio
async def test_my_agent_happy_path():
    input_data = MyAgentInput(submission_id="test", risk_score=0.5)
    output = await run(input_data)
    assert output.action in ["ACCEPT", "DECLINE", "REFER"]
    assert 0.0 <= output.confidence <= 1.0
```

### Update a Prompt

**Step 1: Create new version**
```bash
cp system_prompts_config/agent_prompts/agent_name/v1.0.md \
   system_prompts_config/agent_prompts/agent_name/v1.1.md
# Edit v1.1.md
```

**Step 2: Update registry** (`prompt_registry.py`)
```python
PROMPTS = {
    "agent_name": {
        "v1.0": "...",
        "v1.1": "...",  # New version
    }
}
```

**Step 3: Use in agent**
```python
prompt_text = registry.get("agent_name", version="1.1")
message = await client.messages.create(
    model="claude-sonnet-4-6",
    system=prompt_text,
    messages=[...]
)
# Version automatically logged in cost_ledger
```

### Test Locally

```bash
# Run all tests
uv run pytest backend/tests -v --cov

# Run specific test
uv run pytest backend/tests/api/test_submissions.py -v

# Run with coverage report
uv run pytest backend/tests --cov=backend/src --cov-report=html
# Open htmlcov/index.html
```

### Debug a Failed Submission

```bash
# 1. Check submission status
curl http://localhost:8081/api/v1/submissions/POL-REF \
  -H "X-API-Key: key"

# 2. Check progress
curl http://localhost:8081/api/v1/submissions/{uuid}/progress \
  -H "X-API-Key: key"

# 3. Check cost ledger
curl http://localhost:8081/api/v1/submissions/{uuid}/costs \
  -H "X-API-Key: key"

# 4. Query DB directly
psql -h localhost -U qbe -d aus_underwriting
SELECT * FROM submissions WHERE submission_ref = 'POL-REF';
SELECT * FROM cost_ledger WHERE submission_id = '...' ORDER BY timestamp DESC;

# 5. Check LangGraph checkpoint
SELECT * FROM checkpoint_writes WHERE thread_id = '...';
```

---

## 🚢 Deployment

### Pre-Production Checklist

- [ ] **API Key Management**
  - [ ] Secrets manager configured (not in .env)
  - [ ] Key rotation schedule defined
  - [ ] Audit logging enabled

- [ ] **Environment Variables**
  - [ ] `ANTHROPIC_API_KEY` set in secrets
  - [ ] `DAILY_SPEND_CAP_USD` configured per SLA
  - [ ] `MODEL_*` overrides reviewed
  - [ ] Database connection string production-ready

- [ ] **Database**
  - [ ] Backups configured (nightly)
  - [ ] cost_ledger table archival plan (monthly export)
  - [ ] PostgreSQL 17 + pgvector verified
  - [ ] Connection pooling tuned

- [ ] **Monitoring**
  - [ ] Error logging (Sentry or similar)
  - [ ] Cost dashboard persisted (Grafana)
  - [ ] Pipeline latency tracked
  - [ ] Broker rate limit violations alerting

- [ ] **Security**
  - [ ] SSL/TLS on API endpoint
  - [ ] API key rate limiting enforced
  - [ ] Broker status validation (ACTIVE only)
  - [ ] Prompt injection detection confirmed
  - [ ] CORS configured for frontend origin

- [ ] **Performance**
  - [ ] Load test: 100 concurrent submissions
  - [ ] Query performance: cost_ledger 1M+ rows
  - [ ] LangGraph checkpoint recovery tested
  - [ ] Embedding search latency <100ms

### Deployment Options

#### Option 1: Azure Container Instances (ACI)
```bash
# Build container
docker build -f deployment/Dockerfile -t qbe-underwriting:latest .

# Push to Azure Container Registry
az acr build --registry myregistry --image qbe-underwriting:latest .

# Deploy with docker-compose
az container create \
  --resource-group mygroup \
  --name qbe-underwriting \
  --image myregistry.azurecr.io/qbe-underwriting:latest \
  --environment-variables ANTHROPIC_API_KEY=$KEY
```

#### Option 2: Azure App Service
```bash
# Create web app
az webapp create -g mygroup -p myplan -n qbe-underwriting

# Deploy from local container
az webapp config container set \
  -n qbe-underwriting -g mygroup \
  --docker-custom-image-name myregistry.azurecr.io/qbe-underwriting:latest
```

#### Option 3: Kubernetes (AKS)
```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qbe-underwriting
spec:
  replicas: 3
  selector:
    matchLabels:
      app: qbe-underwriting
  template:
    metadata:
      labels:
        app: qbe-underwriting
    spec:
      containers:
      - name: api
        image: myregistry.azurecr.io/qbe-underwriting:latest
        ports:
        - containerPort: 8081
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: anthropic-secret
              key: api-key
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: connection-string
```

---

## 💡 Code Standards

### Python Style
- **Linter:** Ruff (E, F, I, UP, B, SIM)
- **Type Checker:** mypy (strict mode)
- **Formatter:** Black (via Ruff)
- **Line Length:** 100 characters

```bash
# Check code quality
uv run ruff check backend/src
uv run mypy backend/src
```

### Async Patterns
✅ Do:
```python
async def process():
    result = await some_async_call()
    return result
```

❌ Don't:
```python
def process():
    # Blocking I/O — will freeze the event loop
    result = requests.get(url)
    return result
```

### Database
✅ Do:
```python
async with get_session() as session:
    result = await session.execute(select(Model))
    return result.scalars().all()
```

❌ Don't:
```python
# Session not cleaned up
session = get_session()
result = session.query(Model).all()
```

### Logging
✅ Do:
```python
import logging
logger = logging.getLogger(__name__)
logger.info(f"Processing submission {submission_id}")
```

❌ Don't:
```python
# No logger — logs to stdout
print(f"Processing submission {submission_id}")
```

---

## 🔗 Import Conventions

### Standard Imports
```python
from underwriting.pipeline_agents.document_ingestion_agent.agent import run
from underwriting.database.models import Submission, Customer
from underwriting.database.connection import get_session
from underwriting.platform.orchestration.prompt_registry import PromptRegistry
from underwriting.platform.llm.client import llm_client, MODEL_FOR_AGENT
from underwriting.platform.orchestration.workflow import run_pipeline, resume_pipeline
from underwriting.platform.cost_tracking.middleware import record_llm_cost
```

### Relative Imports (Within Module)
```python
from .schemas import MyInput, MyOutput
from .agent import run
```

---

## 📊 Database Schema Quick Reference

### Submissions Table
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Unique submission ID |
| `submission_ref` | VARCHAR | Broker's policy number |
| `status` | VARCHAR | RECEIVED → COMPLETED / DECLINED |
| `workflow_status` | VARCHAR | ACCEPTED / DECLINED / AWAITING_HUMAN / REFERRED |
| `extracted_data` | JSONB | Output from document ingestion agent |
| `risk_score` | DECIMAL | 0.0–1.0 confidence |
| `pricing_quote` | JSONB | Premium + breakdown |
| `decision_reasoning` | TEXT | Why this decision |
| `class_of_business` | VARCHAR | property, motor, liability, etc. |
| `jurisdiction` | VARCHAR | NZ or AU |
| `created_at` | TIMESTAMP | When submitted |
| `completed_at` | TIMESTAMP | When workflow finished |

### Cost Ledger Table
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Unique cost entry |
| `submission_id` | UUID FK | Link to submission |
| `agent_name` | VARCHAR | Which agent made the call |
| `model_id` | VARCHAR | Model used (haiku, sonnet) |
| `input_tokens` | INT | From response.usage.input_tokens |
| `output_tokens` | INT | From response.usage.output_tokens |
| `cost_usd` | DECIMAL | Calculated from tokens + pricing |
| `prompt_version` | VARCHAR | Prompt version used (for reproducibility) |
| `class_of_business` | VARCHAR | For cost breakdown |
| `jurisdiction` | VARCHAR | For cost breakdown |
| `timestamp` | TIMESTAMP | When call was made |

---

## 🎓 Learning Path

### Day 1: Setup & API
- [ ] Clone repo, run 5-min setup
- [ ] Test `/health` endpoint
- [ ] Review `backend/main.py` (FastAPI wiring)
- [ ] Read `backend/src/underwriting/api/routers/health.py`

### Day 2: Agents
- [ ] Read `backend/src/underwriting/pipeline_agents/document_ingestion_agent/agent.py`
- [ ] Understand `SubmissionData` schema
- [ ] Run ingestion test: `uv run pytest backend/tests/pipeline/test_schemas.py -v`

### Day 3: Workflow
- [ ] Read `backend/src/underwriting/platform/orchestration/workflow.py`
- [ ] Understand StateGraph + node routing
- [ ] Trace through E2E test: `uv run pytest backend/tests/api/test_e2e_pipeline.py -v`

### Day 4: Database & RAG
- [ ] Review `backend/src/underwriting/database/models.py`
- [ ] Check `backend/src/underwriting/pipeline_agents/claims_history_agent/agent.py` (pgvector)
- [ ] Run seed script: `uv run python backend/scripts/admin/seed_data.py`

### Day 5: Deployment & Costs
- [ ] Review Dockerfile + docker-compose.yml
- [ ] Check cost tracking: `backend/src/underwriting/platform/cost_tracking/`
- [ ] View cost dashboard: http://localhost:8501/cost_dashboard

---

## 🐛 Troubleshooting

### Issue: "ProactorEventLoop" error on Windows
**Cause:** Running `uvicorn main:app` directly on Windows.
**Fix:** Use `uv run python run.py` or `start_api.bat` instead.

### Issue: "Broker account is inactive"
**Cause:** Broker status in DB is not "ACTIVE".
**Fix:** 
```bash
psql -h localhost -U qbe -d aus_underwriting
UPDATE brokers SET status = 'ACTIVE' WHERE name = 'Demo Broker';
```

### Issue: Rate limit hit (429)
**Cause:** Broker exceeded 10 requests/day.
**Fix:** Wait until midnight UTC, or increase `DAILY_LIMIT` in `rate_limiter.py`.

### Issue: "No such column: api_keys.api_key_hash"
**Cause:** Missing migration for Phase 2 (broker auth).
**Fix:** Run `uv run alembic upgrade head` to apply all migrations.

### Issue: API starts but Streamlit can't connect
**Cause:** API not running or network error.
**Fix:** 
```bash
# Check API is live
curl http://localhost:8081/health

# Restart both
cd backend && uv run python run.py  # Terminal 1
cd frontend && uv run streamlit run underwriter_portal.py  # Terminal 2
```

### Issue: Embeddings error (sentence-transformers not found)
**Cause:** Dependencies not installed.
**Fix:** `uv sync` to reinstall all deps.

### Issue: "ModuleNotFoundError: No module named 'langgraph.checkpoint.postgres'"
**Cause:** `langgraph-checkpoint-postgres` package not installed.
**Fix:** Run `uv sync` to install all dependencies (includes langgraph-checkpoint-postgres>=3.1.0).

### Issue: "ModuleNotFoundError: No module named 'backend'"
**Cause:** PYTHONPATH not set correctly when running `backend/run.py`.
**Fix:** Use `uv run python backend/run.py` from the project root (not from `backend/` directory). The script auto-adds `backend/src` to sys.path.

---

## 📞 Support

**Code Questions:** Consult the relevant agent's docstring + `agent.py` file.

**Architecture Questions:** See **Architecture** section above.

**Deployment Questions:** See **Deployment** section above.

**Bug Reports:** Check **Troubleshooting** first, then open GitHub issue.

---

## 📚 Further Reading

- **README.md** — User-facing guide (quickstart, endpoints, concepts)
- **system_prompts_config/agent_prompts/README.md** — Prompt versioning
- **backend/scripts/admin/README.md** — Admin utilities
- **Anthropic Docs:** https://docs.anthropic.com/ (models, API, SDK)
- **LangGraph Docs:** https://langchain-ai.github.io/langgraph/ (workflow, checkpointing)

---

## 📝 Version History

| Date | Status | Notes |
|---|---|---|
| 2025-05-30 | ✅ Production Ready | All agents + API + UI complete. Phase 2 (Auth + Rate Limiting) merged. |
| 2025-05-15 | ✅ Phase 2 Complete | API key auth + broker DB + rate limiting. |
| 2025-05-01 | ✅ Phase 1 Complete | 6 agents + workflow + cost tracking. |
| 2025-04-15 | 🚀 Initial Release | MVP with document ingestion + auto-approve. |

---

**Last Updated:** 2025-05-30  
**Maintainer:** Raj Kumar  
**License:** Proprietary (QBE Insurance NZ)
