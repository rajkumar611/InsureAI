# INSUREAI — Enterprise Multi-Agent AI Underwriting System

**Production-ready insurance underwriting platform** powered by multi-agent LLM orchestration (Claude + LangGraph). Processes broker documents through 6 specialized agents → autonomous or human-escalated decisions → real-time cost tracking.

**Live Demo:** http://localhost:8081/docs | http://localhost:8502

---

## 🎯 Project Vision

InsureAI automates routine insurance underwriting decisions while maintaining full auditability and human oversight for complex cases. Built for QBE Insurance NZ as a portfolio project targeting senior AI engineering roles.

**Key Metrics:**
- **6 Pipeline Agents** — document ingestion → claims analysis → hazard evaluation → risk scoring → human queue → pricing
- **2 UI Dashboards** — underwriter portal (Streamlit) + LLM cost analytics
- **100% Async** — FastAPI + asyncpg + LangGraph checkpoint storage
- **Cost-Tracked** — real token counts from Anthropic API logged after every call
- **Auditable** — hash-chained decision logs, version-controlled prompts, full submission history

---

## 📋 Quick Start

### Prerequisites
- Python 3.12+
- Docker Desktop (for PostgreSQL 17 + pgvector)
- `uv` package manager
- API key: `ANTHROPIC_API_KEY` in `.env`

### 1. Start Database

```bash
docker compose up postgres -d
```

### 2. Install & Migrate

```bash
uv sync
uv run alembic upgrade head
```

### 3. Seed Data (Optional)

```bash
uv run python database/admin/seed_data.py        # 15 customers, 15 claims, 8 regulations
uv run python database/admin/seed_brokers.py     # Demo brokers + API keys
```

### 4. Start API (Terminal 1)

```bash
cd backend
uv run python run.py
# or: start_api.bat (Windows)
```

API runs on **http://localhost:8081**
- Docs: http://localhost:8081/docs
- Health: http://localhost:8081/health

### 5. Start Underwriter Portal (Terminal 2)

```bash
cd frontend
uv run streamlit run underwriter_portal.py
# or: start_streamlit.bat (Windows)
```

Streamlit runs on **http://localhost:8501**

### 6. Run Tests

```bash
uv run pytest backend/tests -v --cov
```

---

## 🏗️ Architecture

### System Flow

```
Broker submits document via POST /api/v1/pipeline
        ↓
[1] Document Ingestion Agent (Claude Haiku)
        ├─ Extract text, tables, images
        ├─ Sanitise prompt injection
        ├─ Flag anomalies (missing fields, confidence)
        ↓
[Parallel] Claims History Agent + Hazard Evaluation Agent
        ├─ Claims History: RAG via pgvector (customer benchmark fallback)
        ├─ Hazard: NZ/AU geo-spatial risk scoring
        ↓
[2] Underwriting Risk Agent (Claude Sonnet)
        ├─ Pre-screen rules (deterministic Python)
        ├─ LLM synthesis: confidence scoring
        ├─ Route: ACCEPT / REFER / DECLINE
        ↓
[3] Human Escalation (if REFER)
        ├─ Enqueue to underwriter queue
        ├─ Interrupt LangGraph workflow
        ├─ POST /api/v1/queue/{id}/decision to resume
        ↓
[4] Pricing Agent (Claude Haiku)
        ├─ Apply market rates
        ├─ Calculate loadings/discounts
        ↓
[5] Governance Agent (Claude Sonnet)
        ├─ Final validation
        ├─ Compliance check
        ├─ Sign off
        ↓
Workflow completes → submission status updated → cost ledger recorded
```

### Tech Stack

| Layer | Tech |
|---|---|
| **API** | FastAPI 0.115+ |
| **Agents** | Claude Haiku/Sonnet + LangGraph 1.1+ |
| **Orchestration** | LangGraph StateGraph + PostgreSQL checkpointer |
| **Database** | PostgreSQL 17 + pgvector + async SQLAlchemy 2.0 |
| **Embedding** | sentence-transformers all-MiniLM-L6-v2 (384-dim) |
| **UI** | Streamlit 1.40+ (underwriter + cost dashboard) |
| **Infrastructure** | Docker Compose + Alembic migrations |
| **Auth** | SHA256 API key hashing + rate limiting (10 reqs/day per broker) |

---

## 📁 Folder Structure

```
INSUREAI/
├── README.md                                         This file
├── CLAUDE.md                                         Project guide for Claude Code
├── pyproject.toml                                    Dependencies + project config
├── .env / .env.example                               Environment variables
│
├── frontend/
│   ├── underwriter_portal.py                        Streamlit UI for underwriters
│   ├── cost_dashboard.py                            Streamlit LLM cost analytics
│   ├── start_streamlit.bat                          Launcher (Windows)
│   └── tests/                                        UI tests (if any)
│
├── database/
│   ├── models.py                                     SQLAlchemy ORM models
│   ├── connection.py                                 Async session + connection pool
│   ├── tables_creation.sql                           Raw SQL schema
│   └── admin/                                        Database setup utilities
│       ├── seed_data.py                             Load 15 customers + 15 claims
│       ├── seed_brokers.py                          Create demo brokers + API keys
│       └── health_check_db.py                       Database health check
│
├── backend/
│   ├── main.py                                       FastAPI app entry point
│   ├── run.py                                        Windows event loop fix launcher
│   ├── alembic.ini                                  Database migration config
│   ├── alembic/versions/                            8 migrations (0001-0008)
│   │
│   ├── src/underwriting/
│   │   ├── api/
│   │   │   ├── middleware/
│   │   │   │   ├── auth.py                          SHA256 API key validation
│   │   │   │   ├── rate_limiter.py                  10/day per broker
│   │   │   │   └── logging.py                       JSON request/response logging
│   │   │   └── routers/
│   │   │       ├── health.py                        GET /health, /health/ready
│   │   │       ├── submissions.py                   POST/GET /api/v1/submissions
│   │   │       └── pipeline.py                      POST /api/v1/submissions/pipeline, queue endpoints
│   │   │
│   │   ├── database/
│   │   │   ├── models.py                            SQLAlchemy ORM models (Submission, Broker, ApiKey, CostEntry, etc.)
│   │   │   └── connection.py                        Async session factory + connection pool
│   │   │
│   │   ├── pipeline_agents/
│   │   │   ├── document_ingestion_agent/           [1] Extract + sanitise documents
│   │   │   │   ├── agent.py
│   │   │   │   └── schemas.py                       SubmissionData (24 fields)
│   │   │   ├── claims_history_agent/               [2a] RAG search + fallback benchmark
│   │   │   │   ├── agent.py
│   │   │   │   └── schemas.py                       ClaimsProfile, ClaimsStats
│   │   │   ├── hazard_evaluation_agent/            [2b] Geo-spatial risk scoring
│   │   │   │   ├── agent.py                        NZ/AU keyword lookup
│   │   │   │   └── schemas.py                       HazardScore (level + confidence)
│   │   │   ├── underwriting_risk_agent/            [3] Pre-screen + LLM synthesis
│   │   │   │   ├── agent.py                        Deterministic rules → Claude Sonnet
│   │   │   │   └── schemas.py                       RiskDecision (action + confidence)
│   │   │   ├── human_in_the_loop/                  [4] Queue + interrupt/resume
│   │   │   │   ├── agent.py
│   │   │   │   └── schemas.py                       UnderwriterQueue, UnderwriterDecision
│   │   │   └── pricing_agent/                      [5] Market rates + loadings
│   │   │       ├── agent.py
│   │   │       └── schemas.py                       PricingQuote (premium + breakdown)
│   │   │
│   │   └── platform/
│   │       ├── llm/
│   │       │   ├── client.py                        Shared Anthropic client (model routing)
│   │       │   └── parsing.py                       JSON extraction utilities
│   │       ├── orchestration/
│   │       │   ├── workflow.py                      LangGraph StateGraph + PostgreSQL checkpointer
│   │       │   └── prompt_registry.py               Versioned prompts with {{VAR}} templating
│   │       ├── governance_agent/
│   │       │   ├── agent.py                        [6] Final validation + signing
│   │       │   └── schemas.py
│   │       ├── cost_tracking/
│   │       │   ├── middleware.py                   Record token costs after every LLM call
│   │       │   └── pricing.py                      Calculate USD from token counts
│   │       └── progress_tracker.py                  Real-time pipeline step tracking (Redis-free)
│
├── tests/
│   ├── api/                                         API endpoint tests
│   │   ├── test_health.py
│   │   ├── test_submissions.py
│   │   ├── test_pipeline.py
│   │   └── test_e2e_pipeline.py
│   ├── pipeline/                                    Agent logic tests
│   │   ├── test_pricing.py
│   │   └── test_schemas.py
│   ├── platform/                                    Orchestration tests
│   │   ├── test_workflow_routing.py
│   │   └── test_schemas.py
│   └── dev/                                         Manual debug utilities
│       ├── run_ingestion.py                         Test ingestion agent in isolation
│       └── test_broker_api.py                       E2E API + broker auth test
│
├── deployment/
│   ├── Dockerfile                                   Build container (Python 3.12 + uv)
│   ├── docker-compose.yml                           PostgreSQL 17 + pgvector + API + Dashboard
│   └── start_api.bat                                Batch launcher for API (Windows)
│
├── system_prompts_config/
│   └── agent_prompts/
│       ├── document_ingestion_agent/v1.0.md
│       ├── claims_history_agent/v1.0.md
│       ├── hazard_evaluation_agent/v1.0.md
│       ├── underwriting_risk_agent/v1.0.md
│       ├── pricing_agent/v1.0.md
│       └── governance_agent/v1.0.md
│
├── sample_broker_files/
│   ├── documents/                                   7 test scenarios
│   │   ├── clean_auto_approve.txt
│   │   ├── decline_missing_fields.txt
│   │   ├── decline_prompt_injection.txt
│   │   ├── referral_hazard_zone.txt
│   │   ├── referral_large_claim.txt
│   │   ├── referral_more_claims.txt
│   │   └── referral_sum_insured.txt
│   └── README.md
│
└── evals/
    ├── run_evals.py                                 Performance benchmark script
    └── scenarios.py                                 Test scenarios + expected outcomes
```

---

## 🔌 API Endpoints

### Health & Status

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | ✗ | Liveness check — is process running? |
| `GET` | `/health/ready` | ✗ | Readiness check — DB connectivity |

### Submissions

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/submissions` | ✓ | Register submission (no processing) |
| `GET` | `/api/v1/submissions/{ref}` | ✓ | Fetch by policy number or UUID |
| `POST` | `/api/v1/submissions/ingest` | ✓ | Ingestion agent only (no workflow) |
| `POST` | `/api/v1/submissions/pipeline` | ✓ | Full pipeline (ingest → workflow) |
| `GET` | `/api/v1/submissions/{id}/progress` | ✓ | Real-time progress (step name + timestamp) |

### Queue (Human Escalation)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/queue` | ✓ | List pending items (paginated) |
| `GET` | `/api/v1/queue/{id}` | ✓ | Fetch item with full submission context |
| `POST` | `/api/v1/queue/{id}/decision` | ✓ | Submit underwriter decision → resume pipeline |

### Audit

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/audit/{submission_id}` | ✓ | Audit trail (decisions + prompts + tokens) |

---

## 🔐 Authentication & Rate Limiting

### API Key Setup

1. **Create broker** (via seed or manually):
   ```bash
   # Create demo brokers with API keys
   uv run python database/admin/seed_brokers.py
   ```

2. **Use API key** in requests:
   ```bash
   curl -X POST http://localhost:8081/api/v1/submissions/pipeline \
     -H "X-API-Key: your-api-key-here" \
     -H "Content-Type: application/json" \
     -d '{
       "submission_ref": "POL-2025-001",
       "class_of_business": "property",
       "jurisdiction": "NZ",
       "document_content": "..."
     }'
   ```

### Security Details

- **API Key Hashing:** SHA256 (stored hashed in DB, never logged)
- **Rate Limiting:** 10 submissions/day per broker (configurable via env)
- **Daily Spend Cap:** $10 USD default (via `DAILY_SPEND_CAP_USD` env var)
- **Health Endpoints:** Exempt from auth
- **Broker Status:** Only ACTIVE brokers can submit

---

## 🤖 Agent Details

### 1. Document Ingestion Agent
**Model:** Claude Haiku | **Type:** Deterministic → Extraction

- Reads text/tables/images from document
- Validates against 24 required fields (submission_ref, sum_insured, etc.)
- Detects prompt injection attempts
- Flags anomalies (missing fields, low confidence)
- Output: `SubmissionData` schema

### 2. Claims History Agent
**Model:** Claude Haiku | **Type:** RAG (Fallback Benchmark)

- Tries 3-tier customer match: ABN/NZBN exact → name similarity → vector search
- Queries `claims_embeddings` table (pgvector HNSW index)
- Falls back to benchmark claims (filtered by class of business)
- Returns: claims frequency, avg claim size, fraud history (excluding other fraudsters)

### 3. Hazard Evaluation Agent
**Model:** Claude Sonnet | **Type:** Geo-Spatial Scoring

- Looks up NZ/AU keywords: seismic zones, flood plains, bushfire regions
- Calculates hazard_score (0.0–1.0) + confidence
- Routing: high hazard + frequent claims → auto-DECLINE
- Output: `HazardScore` (level: LOW/MEDIUM/HIGH/EXTREME, confidence)

### 4. Underwriting Risk Agent
**Model:** Claude Sonnet | **Type:** Pre-Screen + LLM Synthesis

**Deterministic Pre-Screen (fires before any LLM):**
- `overall_hazard_level == EXTREME` AND `total_claims_3yr > 2` → DECLINE
- `FRAUD_SUSPICION` in risk flags → DECLINE
- `sum_insured > NZD/AUD 50M` → REFER
- `hazard_score.confidence < 0.50` → REFER
- `extraction_confidence == LOW` → REFER

**LLM Synthesis (if no pre-screen trigger):**
- Claude Sonnet reviews all upstream data
- Outputs `RiskDecision` (action, confidence, reasoning)
- Confidence ≥ 0.70 → auto-ACCEPT, else → REFER (human queue)

### 5. Human-in-the-Loop Agent
**Model:** N/A | **Type:** Queue + Interrupt/Resume

- Creates `UnderwriterQueueItem` if REFER
- Pauses LangGraph workflow via `interrupt()`
- Awaits POST `/api/v1/queue/{id}/decision`
- Resumes with underwriter's action (ACCEPT/DECLINE/REFER)
- Tracks SLA, escalation, decision notes

### 6. Pricing Agent
**Model:** Claude Haiku | **Type:** Market Rate Synthesis

- Applies market rate tables (by class, hazard zone, claims history)
- Calculates loadings (e.g., +20% for MEDIUM hazard)
- Calculates discounts (e.g., −10% for zero claims)
- Output: `PricingQuote` (premium, breakdown, loadings, discounts)

### 7. Governance Agent
**Model:** Claude Sonnet | **Type:** Final Validation

- Consistency check: risk assessment vs. pricing vs. claims data
- Compliance: RBNZ/FMA rules (NZ), APRA rules (AU)
- Fraud signals: cross-references against regulatory databases
- Signs off or escalates to senior underwriter

---

## 💰 Cost Tracking

### Real-Time Cost Recording

Every LLM call logs to `cost_ledger` table:
- **Input Tokens:** from `response.usage.input_tokens`
- **Output Tokens:** from `response.usage.output_tokens`
- **Model ID:** model used (e.g., claude-sonnet-4-6)
- **Cost USD:** calculated from Anthropic's public pricing
- **Agent Name + Metadata:** class_of_business, jurisdiction, feature_tag

### Cost Dashboard

Access via **Streamlit:** http://localhost:8501/cost_dashboard

**Sections:**
- **KPI Row:** Total spend, total calls, total tokens (input/output)
- **Cost by Agent:** Which agent costs most
- **Cost by Model:** Haiku vs Sonnet spend
- **Daily Spend Trend:** Cost over time
- **Cost by Class of Business:** Property vs Motor vs Liability
- **Cost by Jurisdiction:** NZ vs AU
- **Token Efficiency:** Avg tokens/cost per agent
- **Raw Ledger:** Last 100 records (for debugging)

**Pricing (as of Feb 2025):**
- **Claude Haiku:** $0.80/1M input, $4.00/1M output
- **Claude Sonnet:** $3.00/1M input, $15.00/1M output

---

## 📊 Database Schema

### Core Tables

| Table | Purpose |
|---|---|
| `submissions` | Master record for each underwriting case |
| `customers` | Broker customers (by ABN/NZBN) |
| `claims` | Historical claims for customers |
| `claims_embeddings` | pgvector embeddings (384-dim, HNSW index) |
| `brokers` | API consumer accounts |
| `api_keys` | Broker API keys (SHA256 hashed) |
| `underwriter_queue` | Escalated submissions awaiting human review |
| `cost_ledger` | LLM token costs (one row per call) |

### Migrations

8 migrations from initial schema to current state:
- 0001: Initial schema (submissions, customers, claims)
- 0002: pgvector 1536 → 384-dim optimization
- 0003: Customer/policy/claim enhancements
- 0004: Extracted data fields on submissions
- 0005: Pipeline state snapshot on queue items
- 0006: Widen prompt_version VARCHAR
- 0007: Add brokers + API keys tables (Phase 2)
- 0008: Drop audit trail (checkpoint-based instead)

---

## 🧪 Testing

### Run All Tests

```bash
uv run pytest backend/tests -v --cov
```

### Test Categories

| Path | Purpose |
|---|---|
| `backend/tests/api/` | Endpoint tests (health, submissions, pipeline) |
| `backend/tests/pipeline/` | Agent logic (pricing, schemas, input validation) |
| `backend/tests/platform/` | Workflow routing, checkpointer behavior |

### Example: Test Full Pipeline

```bash
uv run pytest backend/tests/api/test_e2e_pipeline.py -v
```

---

## 🚀 Deployment

### Docker Compose (Local)

```bash
docker compose up
# Spins up: PostgreSQL (5432) + API (8000) + Dashboard (8501)
```

### Production Deployment

See deployment best practices in **CLAUDE.md** → Deployment Strategy.

Quick checklist:
- [ ] Set `ANTHROPIC_API_KEY` in production secrets
- [ ] Configure `DAILY_SPEND_CAP_USD` per SLA
- [ ] Enable Broker status validation (ACTIVE only)
- [ ] Enable API key rotation + audit logging
- [ ] Backup cost_ledger table (archival queries)
- [ ] Monitor LangGraph checkpoint recovery (checkpoint_config)

---

## 📚 Key Concepts

### LangGraph Workflow
- **StateGraph:** Directed acyclic graph of agent nodes
- **PostgreSQL Checkpointer:** Persist state after each step (recovery + replay)
- **Interrupt:** Pause workflow at human-in-the-loop node, resume with underwriter decision
- **Parallel:** Claims + Hazard agents run async via `asyncio.gather()`

### Embeddings & RAG
- **Model:** sentence-transformers all-MiniLM-L6-v2 (384-dim, ~80MB)
- **Index:** pgvector HNSW (fast approximate search)
- **Retrieval:** Top 3 claims by similarity, ranked by relevance score

### Prompt Versioning
- All agent prompts versioned (e.g., `document_ingestion_agent/v1.0.md`)
- Version recorded in `cost_ledger` for reproducibility
- Upgrades: new version number, A/B test with submissions

### Audit Trail
- Submissions table: status, extracted_data, risk_score, pricing, decision
- Cost ledger: token counts + cost per call
- LangGraph checkpoints: full workflow state snapshots
- No separate audit table — all audit via submission history + cost ledger

---

## 🛠️ Development Workflow

### Add a New Agent

1. Create folder under `backend/src/underwriting/pipeline_agents/my_agent/`
2. Define `schemas.py` (Pydantic input/output models)
3. Implement `agent.py` (async function returning output)
4. Add node to `backend/src/underwriting/platform/orchestration/workflow.py`
5. Register model choice in `backend/src/underwriting/platform/llm/client.py`
6. Write tests in `backend/tests/pipeline/test_my_agent.py`

### Update a Prompt

1. Edit version file: `system_prompts_config/agent_prompts/agent_name/v1.1.md`
2. Update version in `prompt_registry.py`
3. Reference via `registry.get("agent_name", version="1.1")`
4. Log which version was used in cost_ledger (for debugging)

### Run Local Dev

```bash
# Terminal 1: Database
docker compose up postgres -d

# Terminal 2: API with hot reload
cd backend && uv run python run.py

# Terminal 3: Streamlit with hot reload
cd frontend && uv run streamlit run underwriter_portal.py

# Terminal 4: Run tests as you develop
watch -n 2 'uv run pytest backend/tests -q'
```

---

## 🎓 Learning Resources

### Code Organization
- **Agents:** each has `agent.py` + `schemas.py` for clarity
- **Middleware:** FastAPI middleware for auth + rate limiting
- **Database:** async SQLAlchemy 2.0 patterns (mapped_column, Mapped)
- **Async:** all I/O ops use `await` (no blocking calls)

### Claude Integration
- **Anthropic SDK:** v0.40+ with token counting
- **Prompt Caching:** prompts stored in registry for reuse
- **Model Routing:** environment variables override default models
- **Vision (if enabled):** agent can read images from documents

### LangGraph Patterns
- **StateGraph:** nodes as async functions, edges as routes
- **Interrupt:** `Command(goto="...", resume=data)`
- **Checkpointing:** PostgreSQL persists state for recovery
- **Tool Use:** agents can call Python functions (not exposed here)

---

## 📖 Further Reading

- **CLAUDE.md** — Full project guide for Claude Code
- **system_prompts_config/agent_prompts/README.md** — Prompt templates
- **database/admin/** — Database admin utilities (seed_data, seed_brokers, health_check_db)
- **deployment/** — Dockerfile, docker-compose.yml setup

---

## 🔗 Links

| Resource | URL |
|---|---|
| **API Docs (Swagger)** | http://localhost:8081/docs |
| **API Redoc** | http://localhost:8081/redoc |
| **Underwriter Portal** | http://localhost:8501 |
| **Cost Dashboard** | http://localhost:8501/?page=cost_dashboard |
| **GitHub** | https://github.com/rajkumar611/INSUREAI (if public) |

---

## 📧 Support & Feedback

**Issues:** Submit via GitHub Issues or email.

**Questions about code?** Consult **CLAUDE.md** or the relevant agent's `agent.py` + docstrings.

---

## 📝 License

© 2025 Raj Kumar / QBE Insurance NZ. Proprietary.

---

**Last updated:** 2025-05-30  
**Status:** ✅ Production-Ready (All agents, API, UI complete)
