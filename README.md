# InsureAI — Multi-Agent AI Insurance Underwriting System

**Production-ready platform for automated insurance underwriting decisions** powered by multi-agent LLM orchestration (Claude + LangGraph). Processes documents through 6 specialized agents → autonomous or human-escalated decisions → real-time cost tracking.

---

## 🎯 Overview

InsureAI automates routine underwriting decisions while maintaining full auditability and human oversight for complex cases. Built as a portfolio project for AI engineering roles, demonstrating:

- **Multi-Agent Orchestration** — LangGraph StateGraph with PostgreSQL checkpointing
- **RAG (Retrieval-Augmented Generation)** — 3-tier customer match for claim history
- **Cost Transparency** — Real token counts logged per LLM call
- **Human-in-the-Loop** — Interrupt/resume workflows for underwriter review
- **Production Ready** — Async/await, comprehensive testing, Docker deployment

**Tech Stack:** FastAPI · Claude Haiku/Sonnet · LangGraph · PostgreSQL + pgvector · Streamlit

---

## ⚡ Quick Start (5 Minutes)

### Prerequisites
```bash
python --version              # Python 3.12+
docker --version              # Docker Desktop running
uv --version                  # uv package manager (pip install uv)
echo $ANTHROPIC_API_KEY       # Must be set in environment
```

### Setup

```bash
# 1. Start database
docker compose up postgres -d

# 2. Install dependencies
uv sync

# 3. Seed test data (optional)
uv run python database/admin/seed_data.py

# 4. Terminal 1: Start API
cd backend && uv run python run.py

# 5. Terminal 2: Start Dashboard
cd frontend && uv run streamlit run underwriter_portal.py

# 6. Terminal 3: Run tests
uv run pytest backend/tests -v
```

Once running:
- **API:** Available on `http://localhost:8081` (Swagger docs at `/docs`)
- **Dashboard:** Available on `http://localhost:8501`

---

## 🏗️ Architecture

### Pipeline Flow

```
Submit document → [1] Document Ingestion
                      ↓
                   [Parallel]
                   ├─ [2a] Claims History (RAG)
                   └─ [2b] Hazard Evaluation
                      ↓
                   [3] Risk Scoring
                      ├─ Pre-screen rules
                      ├─ LLM synthesis
                      └─ Route: ACCEPT / REFER / DECLINE
                      ↓
                   [4] Human Escalation (if REFER)
                      ├─ Enqueue
                      ├─ Await underwriter decision
                      └─ Resume workflow
                      ↓
                   [5] Pricing
                   [6] Governance
                      ↓
                   Submission complete
```

### 6 Agents

| Agent | Model | Purpose |
|-------|-------|---------|
| Document Ingestion | Haiku | Extract text, validate fields, detect injection |
| Claims History | Haiku | RAG: find customer's claim history |
| Hazard Evaluation | Sonnet | Geo-spatial risk scoring (NZ/AU) |
| Risk Scoring | Sonnet | Pre-screen rules + LLM synthesis |
| Human Escalation | N/A | Queue + interrupt/resume for REFER cases |
| Pricing | Haiku | Apply market rates, loadings, discounts |
| Governance | Sonnet | Final validation + compliance |

### Key Design Decisions

1. **Deterministic Pre-Screen First** — High-confidence rules before expensive LLM calls
2. **Parallel Execution** — Claims + Hazard run simultaneously (no ordering constraints)
3. **PostgreSQL Checkpointing** — Workflow state persisted for recovery + replay
4. **Cost Transparency** — Every token counted, every call logged
5. **Public API** — Direct underwriter submission, no authentication required

---

## 📋 API Endpoints

### Health & Monitoring
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/health/ready` | Readiness check (DB connectivity) |

### Submissions
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/submissions/pipeline` | Submit document + run full workflow |
| `GET` | `/api/v1/submissions/{ref}` | Fetch submission by ref or UUID |
| `GET` | `/api/v1/submissions/{id}/progress` | Real-time pipeline step |

### Human Queue (Escalations)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/queue` | List pending escalations |
| `POST` | `/api/v1/queue/{id}/decision` | Submit underwriter decision → resume |

### Example: Submit Document

```bash
curl -X POST http://localhost:8081/api/v1/submissions/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "submission_ref": "POL-2025-001",
    "class_of_business": "property",
    "jurisdiction": "NZ",
    "document_content": "Insurance application for residential property in Auckland..."
  }'

# Response (202 Accepted):
# {
#   "submission_id": "uuid",
#   "submission_ref": "POL-2025-001",
#   "status": "PROCESSING",
#   "message": "Pipeline started"
# }
```

---

## 🤖 Agent Workflows

### 1. Document Ingestion → Auto-Decision (ACCEPT/DECLINE)

**Time:** ~5-10 seconds | **Cost:** $0.01–0.02 USD

1. Document ingestion extracts structured data
2. Pre-screen rules (deterministic) evaluate → ACCEPT or DECLINE
3. Pipeline completes

### 2. Document → Human Escalation (REFER)

**Time:** Depends on underwriter | **Cost:** $0.02–0.05 USD (LLM only)

1. Document ingestion extracts structured data
2. Claims history + Hazard evaluation run in parallel
3. Risk scoring triggers pre-screen rule → REFER (e.g., high hazard + claims)
4. Submission enqueued to `POST /api/v1/queue`
5. Underwriter reviews, submits decision
6. Pricing + Governance run
7. Pipeline completes

---

## 💰 Cost Tracking

Every LLM call logs to `cost_ledger`:
- **Input Tokens** from `response.usage.input_tokens`
- **Output Tokens** from `response.usage.output_tokens`
- **Cost USD** calculated from token counts

**Pricing (Feb 2025):**
- Claude Haiku: $0.80/1M input, $4.00/1M output
- Claude Sonnet: $3.00/1M input, $15.00/1M output

**View Dashboard:** http://localhost:8501 → LLM Cost Dashboard (embedded in portal)

---

## 📊 Database Schema

### Core Tables

| Table | Purpose |
|-------|---------|
| `submissions` | Master case record (status, extracted data, risk score, pricing) |
| `customers` | Customer records indexed by ABN/NZBN |
| `claims` | Historical claim records (cause, amount, date) |
| `claims_embeddings` | pgvector embeddings (384-dim HNSW index) for RAG |
| `underwriter_queue` | Escalated submissions awaiting human decision |
| `cost_ledger` | LLM token costs (one row per API call) |


---

## 🧪 Testing

```bash
# Run all tests with coverage
uv run pytest backend/tests -v --cov

# Specific test file
uv run pytest backend/tests/api/test_pipeline.py -v

# E2E workflow test
uv run pytest backend/tests/integration/test_e2e_pipeline.py -v
```

**Test Categories:**
- `backend/tests/api/` — Endpoint tests (health, submissions, pipeline)
- `backend/tests/pipeline/` — Agent logic (pricing, schemas)
- `backend/tests/integration/` — Full workflow E2E tests

---

## 🚀 Deployment

### Local Docker

```bash
docker compose up
# Starts: PostgreSQL (5432) + API (8081) + Dashboard (8501)
```

### Production

See **Project_Documentation/K8s_Deployment_Checklist.md** for AWS EKS deployment checklist.

Key steps:
1. Build Docker image
2. Push to ECR
3. Apply Kubernetes manifests (namespace, secrets, deployments, services)
4. Verify pods + LoadBalancer external IPs

---

## 🛠️ Development

### Add a New Agent

1. Create folder: `backend/src/underwriting/pipeline_agents/my_agent/`
2. Define schemas: `schemas.py` (Pydantic input/output)
3. Implement agent: `agent.py` (async function)
4. Register in workflow: `backend/src/underwriting/platform/orchestration/workflow.py`
5. Register model: `backend/src/underwriting/platform/llm/client.py`
6. Write tests: `backend/tests/pipeline/test_my_agent.py`

### Update a Prompt

1. Create new version: `system_prompts_config/agent_name/v1.1.md`
2. Update registry: `backend/src/underwriting/platform/orchestration/prompt_registry.py`
3. Use version in agent: `registry.get("agent_name", version="1.1")`

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| **Project_Documentation/AI_Challenges_and_Solutions.md** | 10 LLM/agent design challenges (multi-agent, RAG, cost tracking, etc.) |
| **Project_Documentation/Approach_and_Phases.md** | Project evolution, design decisions, lessons learned |
| **Project_Documentation/Deployment_Issues_and_Solutions.md** | Comprehensive issues (AI, LLM, AWS, K8s, CI/CD) |
| **Project_Documentation/K8s_Deployment_Checklist.md** | AWS EKS deployment guide |
| **CLAUDE.md** | Detailed developer reference (architecture, workflows, troubleshooting) |

---

## 🔗 Resources

- **Anthropic Docs:** https://docs.anthropic.com/
- **LangGraph Docs:** https://langchain-ai.github.io/langgraph/
- **FastAPI:** https://fastapi.tiangolo.com/
- **Streamlit:** https://docs.streamlit.io/

---

## 🚧 Future Enhancements (Roadmap)

### Phase 4+: Platform Expansion

| Feature | Purpose | Complexity |
|---------|---------|-----------|
| **Broker Portal + API Keys** | Self-service broker registration, API key generation + rotation, usage analytics | Medium |
| **Subnet Routing for External IPs** | Dedicated subnet configuration for LoadBalancer services, static IP pools | Medium |
| **LangSmith Integration** | Real-time tracing + debugging of agent execution, prompt testing framework | Medium |
| **MCP Servers (Claims Data)** | Model Context Protocol integration with external claims databases (RMS, ICBC) | High |
| **Real-Time Notifications** | WebSocket support for underwriter portal (live updates on escalations) | Medium |
| **Document Vision** | Claude's vision API for image extraction (tables, charts, signatures) | Medium |
| **Observability Stack** | Prometheus metrics + Grafana dashboards (latency, token usage, decision distribution) | Medium |
| **Webhook Callbacks** | Outbound notifications on submission completion (to broker systems) | Low |
| **Prompt A/B Testing** | Framework for testing prompt versions with submission sampling | Low |
| **Multi-Language Support** | Document processing in NZ English, Australian English, Te Reo Māori | High |
| **Risk Database Integration** | Real-time hazard data from external providers (GIS, flood models) | High |
| **Custom Reporting** | Export submission data, cost breakdowns, underwriter performance reports | Low |
| **Token Caching** | LLM prompt caching for frequently-used reference documents | Low |
| **Advanced Rate Limiting** | Token-based limits (not just request count) + tiered pricing tiers | Medium |

### Why These Matter

- **Broker Portal** → Multi-tenant platform (SaaS scaling)
- **LangSmith** → Debug agent failures, optimize prompts, audit decisions
- **MCP Servers** → Real-time external data integration (not static databases)
- **Observability** → Production monitoring + cost optimization
- **Vision** → Unlocks scanned documents (PDFs, images)
- **Webhooks** → Async notification to broker systems

---

## ⚠️ Known Limitations

- **Underwriter Authentication:** Placeholder only (no Azure AD integration yet)
- **Single Instance:** Rate limiting via in-memory store (use Redis for multiple instances)
- **Streamlit UI:** MVP dashboard (production would use React)
- **Static Data:** Claims data seeded, not live integration with external systems
- **No Document Vision:** Currently text-only processing

---

## 📝 Project Info

**Status:** Production-Ready (All agents, API, UI complete)  
**Last Updated:** 2026-06-01  
**License:** Proprietary
