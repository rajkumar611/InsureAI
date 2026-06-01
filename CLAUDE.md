# INSUREAI — Claude Code Project Guide

**Enterprise multi-agent AI insurance underwriting platform with public API.**

> **API Access:** Direct underwriter submission via public REST API (no authentication). Perfect for SaaS integration and automated workflows.

---

## 📌 Quick Navigation

- **[Getting Started](#getting-started)** — Run locally in 5 minutes
- **[Project Status](#project-status)** — What's complete
- **[Architecture](#architecture)** — How it works
- **[File Organization](#file-organization)** — Where to find things
- **[Key Workflows](#key-workflows)** — End-to-end flows
- **[Development](#development)** — How to extend
- **[Deployment](#deployment)** — Production checklist
- **[Future Enhancements](#-future-enhancements-phase-4)** — Phase 4+ features and roadmap

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
cd INSUREAI

# 2. Start PostgreSQL
docker compose up postgres -d

# 3. Install dependencies
uv sync

# 4. Seed sample data (optional)
uv run python database/admin/seed_data.py

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
| **Public API** | ✅ DONE | Direct underwriter submission, no authentication required |
| **Streamlit UIs** | ✅ DONE | Underwriter portal (submit, queue, lookup) + cost dashboard |
| **Cost Tracking** | ✅ DONE | Real token counts logged, cost_ledger table, USD calculations |
| **Database** | ✅ DONE | 8 migrations, customers, claims, queue, cost ledger, embeddings |
| **RAG + Embeddings** | ✅ DONE | pgvector HNSW index, 3-tier customer match, benchmark fallback |
| **Audit Trail** | ✅ DONE | Via submission history + cost_ledger + LangGraph checkpoints |
| **Tests** | ✅ DONE | API tests, pipeline tests, workflow routing tests, E2E tests |
| **Docker Deployment** | ✅ DONE | Dockerfile, docker-compose.yml, start scripts (Windows + POSIX) |

### 🔄 Future (Phase X+)

| Feature | Status | Purpose |
|---|---|---|
| **Underwriter Authentication** | ⏸️ | Azure AD SSO + role-based access control |
| **Redis Rate Limiter** | ⏸️ | For distributed deployment (multi-instance) |
| **Webhook Notifications** | ⏸️ | Real-time submission status callbacks |
| **React Frontend** | ⏸️ | Production SPA (currently using Streamlit) |

---

## 🚧 Future Enhancements (Phase 4+)

### Broker Portal & Multi-Tenancy
**Goal:** Self-service platform for external brokers to submit policies

```
Features:
- Broker self-registration (name, company, contact)
- API key generation + rotation
- Usage dashboard (submissions/month, cost, success rate)
- Rate limiting per broker tier (bronze/silver/gold)
- Bulk submission CSV upload
```

**Why:** SaaS scaling — currently single-user underwriter portal

---

### LangSmith Integration
**Goal:** Real-time tracing + debugging of agent execution

```
Integrations:
- Trace every LLM call with inputs/outputs
- Track decision tree (which rules fired, which agent made final decision)
- A/B test prompt versions with submission sampling
- Debug failures (which step failed, why)
- Performance metrics (latency per agent, token efficiency)
```

**Why:** Production debugging + prompt optimization

---

### MCP Servers for External Data
**Goal:** Real-time integration with external claims databases via Model Context Protocol

```
Targets:
- RMS (Risk Management Solutions) — hazard data
- ICBC (International Bureau of Cargo Insurers) — fraud data
- GIS databases — flood plains, seismic zones, bushfire regions
- Regulatory databases — sanctions lists, compliance checks

Pattern:
- Define MCP server interface (request hazard data, verify customer, check fraud)
- LangGraph calls MCP server as a node
- Results cached + logged to cost_ledger (MCP calls treated as LLM calls)
```

**Why:** Real-time data beats static seeding. Unlocks external risk sources.

---

### Advanced Observability
**Goal:** Production monitoring stack

```
Components:
- Prometheus exporter for metrics
  * Pipeline latency (by agent, by class of business)
  * Token usage (input/output, cost per decision)
  * Decision distribution (ACCEPT %, REFER %, DECLINE %)
  * Queue depth + SLA compliance
  
- Grafana dashboards
  * Cost per submission over time
  * Agent performance comparison
  * Underwriter queue health
  
- Structured logging (JSON to ELK stack)
  * Every agent execution logged with inputs/outputs
  * Decision reasoning captured
  * Errors + retries tracked
```

**Why:** Understand system behavior in production. Optimize costs.

---

### Document Vision (Images + OCR)
**Goal:** Support scanned documents, PDFs with images

```
Implementation:
- Use Claude's vision API in document_ingestion_agent
- Extract text from images, tables, charts
- Validate signature presence (compliance check)
- Handle multi-page documents (parallel processing per page)
```

**Why:** Most insurance documents are scanned PDFs, not plain text.

---

### Subnet Masking for External IPs
**Goal:** Dedicated subnet configuration for LoadBalancer services

```
Current Issue:
- ELB auto-discovers subnets via tags
- No control over which subnets get external IPs
- IPs assigned from AWS pool (not static)

Solution:
- Create dedicated public subnet for LoadBalancer services
- Tag with kubernetes.io/role/external-elb
- Optional: Reserve Elastic IPs for static addresses
- Provides IP whitelist capability for brokers
```

**Why:** IP whitelisting + network isolation for production

---

### Webhook Callbacks
**Goal:** Async notification to broker systems

```
Pattern:
- Submission completes → trigger webhook
- POST to broker's URL with decision + pricing + cost
- Exponential backoff retry logic
- Webhook signing (HMAC SHA256) for security
- Webhook history in dashboard (success/failure)
```

**Why:** Brokers integrate without polling. Decouples broker system from InsureAI.

---

### Advanced Rate Limiting
**Goal:** Token-based limits + tiered pricing

```
Current:
- 10 requests/day per broker (crude)

Future:
- Token bucket: measure by LLM token usage, not request count
  * Bronze tier: 1M tokens/month ($50)
  * Silver tier: 10M tokens/month ($400)
  * Gold tier: unlimited ($5k/month)
  
- Priority queue: high-tier brokers jump queue

- Cost attribution: each broker sees their cost breakdown
```

**Why:** Fair pricing (token usage = cost) + incentivizes efficiency

---

### Prompt A/B Testing Framework
**Goal:** Test prompt variations against submission sample

```
Pattern:
- Define prompt variants (v1.0, v1.1)
- Route % of submissions to each variant
- Measure outcomes (ACCEPT rate, confidence, cost)
- Statistical test: chi-squared goodness-of-fit
- Auto-promote winner to production
```

**Why:** Data-driven prompt optimization

---

### Multi-Language Support
**Goal:** Process documents in English, Te Reo Māori, other NZ languages

```
Implementation:
- Detect language in document_ingestion_agent
- Use language-specific prompts (from prompt_registry)
- Translate output to English for downstream agents
- Track submissions by language (analytics)
```

**Why:** Accessibility + Māori language rights (NZ regulatory trend)

---

### Real-Time Notifications
**Goal:** WebSocket support for underwriter portal

```
Features:
- Live queue updates (new escalation → instant notification)
- Cost dashboard real-time updates
- Decision feedback loop (show underwriter impact on cost/timing)
- Streaming LLM results (show reasoning as it's generated)
```

**Why:** Better UX for high-volume underwriters

---

### Custom Reporting
**Goal:** Export + analytics for underwriters + management

```
Reports:
- Submission volume (daily, weekly, monthly trends)
- Cost breakdown (by agent, by class of business, by jurisdiction)
- Decision distribution (ACCEPT %, REFER %, DECLINE %)
- Underwriter performance (queue depth, SLA compliance, overrides)
- Fraud detection (claims flagged, patterns identified)

Export formats:
- CSV for Excel
- PDF for stakeholders
- Scheduled email delivery
```

**Why:** Business intelligence + compliance reporting

---

### Implementation Priority

**Phase 4 (High Impact, Medium Effort):**
1. LangSmith integration (debug production issues)
2. Subnet masking (production networking)
3. Observability stack (understand costs)

**Phase 5 (High Impact, High Effort):**
1. MCP servers for external data
2. Broker portal + multi-tenancy
3. Document vision (scanned documents)

**Phase 6+ (Nice-to-Have):**
1. Webhook callbacks
2. Advanced rate limiting
3. Prompt A/B testing
4. Multi-language support
5. Real-time WebSocket notifications
6. Custom reporting

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

6. **Public API Design:** Stateless, scalable, no authentication
   - Direct submission without authentication overhead
   - Full transparency: cost, decisions, audit trail visible
   - Rate limiting handled at infrastructure layer (nginx/API gateway)

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
├── start_streamlit.bat                ← Batch launcher (Windows)
└── tests/                             ← UI integration tests (if any)
```

### backend/ — FastAPI + Agents

```
backend/
├── main.py                            ← FastAPI app
├── run.py                             ← Windows launcher (event loop fix)
│
├── api/
│   ├── middleware/
│   │   └── logging.py                ← JSON request/response logging
│   └── routers/
│       ├── health.py                 ← /health, /health/ready
│       ├── submissions.py            ← /api/v1/submissions/* (CRUD)
│       └── pipeline.py               ← /api/v1/submissions/pipeline, /queue/*
│
├── pipeline_agents/
│   ├── document_ingestion_agent/      ← [1] Extract + validate
│   │   ├── agent.py                  ← Main logic
│   │   └── schemas.py                ← SubmissionData (24 fields)
│   │
│   ├── claims_history_agent/         ← [2a] RAG search
│   │   ├── agent.py                  ← 3-tier customer match
│   │   └── schemas.py                ← ClaimsProfile, ClaimsStats
│   │
│   ├── hazard_evaluation_agent/      ← [2b] Geo-spatial risk
│   │   ├── agent.py                  ← NZ/AU keyword lookup
│   │   └── schemas.py                ← HazardScore (level, confidence)
│   │
│   ├── underwriting_risk_agent/      ← [3] Pre-screen + synthesis
│   │   ├── agent.py                  ← Deterministic rules + Sonnet
│   │   └── schemas.py                ← RiskDecision (action, confidence)
│   │
│   ├── human_in_the_loop/            ← [4] Queue + interrupt/resume
│   │   ├── agent.py                  ← Enqueue + workflow pause
│   │   └── schemas.py                ← UnderwriterQueue, Decision
│   │
│   └── pricing_agent/                ← [5] Market rates
│       ├── agent.py                  ← Apply loadings/discounts
│       └── schemas.py                ← PricingQuote
│
└── engine/
    ├── llm/
    │   ├── client.py                 ← Shared Anthropic client (model routing)
    │   └── parsing.py                ← JSON extraction utilities
    │
    ├── orchestration/
    │   ├── workflow.py               ← LangGraph StateGraph + checkpointer
    │   └── prompt_registry.py        ← Versioned prompts with templating
    │
    ├── governance_agent/             ← [6] Final validation + compliance
    │   ├── agent.py
    │   └── schemas.py
    │
    ├── cost_tracking/
    │   ├── middleware.py             ← Record costs after each LLM call
    │   └── pricing.py                ← Calculate USD from token counts
    │
    └── progress_tracker.py           ← Real-time pipeline progress tracking
```

### database/ — ORM Models & Setup Scripts

```
database/
├── connection.py                      ← Async session + PostgreSQL pool
├── models.py                          ← SQLAlchemy ORM models
└── admin/
    ├── db_creation.py                 ← Create database + tables + indexes (DROP & recreate)
    ├── health_check_db.py             ← Database health check
    ├── seed_data.py                   ← Load 15 customers + 120 claims
    └── schema_reference.sql           ← Raw SQL schema (reference)
```

### tests/ — Automated Tests

```
tests/
├── conftest.py                        ← Pytest fixtures + setup
├── api/
│   ├── middleware/
│   │   └── (middleware tests)
│   └── routers/
│       ├── test_health.py            ← Health check tests
│       ├── test_submissions.py       ← Submission CRUD tests
│       └── test_pipeline.py          ← Pipeline endpoint tests
└── (additional integration/unit tests)
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

### prompts/ — Agent System Prompts

```
prompts/
├── document_ingestion_agent/v1.0.md
├── claims_history_agent/v1.0.md
├── hazard_evaluation_agent/v1.0.md
├── underwriting_risk_agent/v1.0.md
├── pricing_agent/v1.0.md
└── governance_agent/v1.0.md
```

### sample_broker_files/ — Test Data & Scenarios

```
sample_broker_files/
├── documents/                         ← 7 test scenarios for E2E validation
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
# Public API — no authentication required

curl -X POST http://localhost:8081/api/v1/submissions/pipeline \
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
curl http://localhost:8081/api/v1/submissions/POL-2025-001

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
# Public API — no authentication required

curl -X POST http://localhost:8081/api/v1/submissions/pipeline \
  -H "Content-Type: application/json" \
  -d '{"submission_ref": "POL-2025-002", ...}'

# Response:
{
  "status": "PROCESSING",
  "submission_id": "uuid-2"
}

# Poll — when ready:
curl http://localhost:8081/api/v1/submissions/uuid-2

# Response when AWAITING_HUMAN:
{
  "status": "AWAITING_HUMAN",
  "workflow_status": "AWAITING_HUMAN",
  "message": "Escalated to underwriter queue"
}

# Underwriter checks queue:
curl http://localhost:8081/api/v1/queue

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
  -H "Content-Type: application/json" \
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
# Or query raw (public access):

curl http://localhost:8081/api/v1/submissions/uuid-2/cost

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

### Architecture: Two Seeding Layers

```
database/admin/
├── init_db.py              ← [0] CREATE schema (tables + indexes)
├── seed_data.py            ← [1] LOAD business domain data
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
**Use Case:** When underwriter submits "Pacific Properties", RAG search finds their historical claims
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

### Complete Setup Flow

```bash
# Step 1: Initialize schema (tables + indexes)
uv run python database/admin/init_db.py

# Step 2: Load test customer data + claims history
uv run python database/admin/seed_data.py

# Step 3: Verify database is healthy
uv run python database/admin/health_check_db.py

# Step 4: Start API and test
uv run python backend/run.py
# In another terminal:
uv run pytest backend/tests -v
```

### ⚠️ Future: Underwriter User Management (Phase X)

**Current Status:** `assigned_underwriter_id` is VARCHAR (no formal User table yet).

**What's Missing:**
- User authentication (Azure AD bearer tokens)
- Role-based access control (Senior UW, Junior UW, Manager)
- Audit trail of WHO made each decision
- Department-specific workflow routing

**When to Add:** When integrating with enterprise authentication system.

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
cp system_prompts_config/agent_name/v1.0.md \
   system_prompts_config/agent_name/v1.1.md
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
curl http://localhost:8081/api/v1/submissions/POL-REF

# 2. Check progress
curl http://localhost:8081/api/v1/submissions/{uuid}/progress

# 3. Check cost ledger
curl http://localhost:8081/api/v1/submissions/{uuid}/costs

# 4. Query DB directly
psql -h localhost -U dbinsureai -d aus_underwriting
SELECT * FROM submissions WHERE submission_ref = 'POL-REF';
SELECT * FROM cost_ledger WHERE submission_id = '...' ORDER BY timestamp DESC;

# 5. Check LangGraph checkpoint
SELECT * FROM checkpoint_writes WHERE thread_id = '...';
```

---

## 🚢 Deployment

### Pre-Production Checklist

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
  - [ ] Submission volume metrics tracked

- [ ] **Security**
  - [ ] SSL/TLS on API endpoint
  - [ ] Rate limiting at infrastructure layer (nginx/API gateway)
  - [ ] Prompt injection detection confirmed
  - [ ] CORS configured for frontend origin
  - [ ] Input validation on all endpoints

- [ ] **Performance**
  - [ ] Load test: 100 concurrent submissions
  - [ ] Query performance: cost_ledger 1M+ rows
  - [ ] LangGraph checkpoint recovery tested
  - [ ] Embedding search latency <100ms

### Deployment Options

See **Project_Documentation/K8s_Deployment_Checklist.md** for production EKS deployment on AWS.

Quick local testing with Docker:
```bash
docker compose up
# Spins up: PostgreSQL (5432) + API (8081) + Dashboard (8501)
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
| `submission_ref` | VARCHAR | External reference (policy/quote number) |
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

📧 **Contact:** crajkumar.6@gmail.com

---

## 📝 Version History

| Date | Status | Notes |
|---|---|---|
| 2025-05-30 | ✅ Production Ready | All agents + API + UI complete. Phase 2 (Auth + Rate Limiting) merged. |
| 2025-05-15 | ✅ Phase 2 Complete | Logging + validation (broker auth removed). |
| 2025-05-01 | ✅ Phase 1 Complete | 6 agents + workflow + cost tracking. |
| 2025-04-15 | 🚀 Initial Release | MVP with document ingestion + auto-approve. |

---

**Last Updated:** 2026-06-01  
**License:** Proprietary
