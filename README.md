# AI Underwriting System

Enterprise-grade multi-agent AI system for insurance underwriting. Built with Python, LangGraph, Claude (Anthropic), FastAPI, and PostgreSQL.

## What This System Does

A broker submits insurance documents. The system:
1. Extracts and validates data from broker documents (OCR + LLM)
2. Retrieves past claims history (RAG over historical data)
3. Evaluates property and environmental hazards
4. Synthesises a risk decision (Accept / Decline / Refer)
5. Routes referred cases to a human underwriter for review
6. Calculates premium and policy terms
7. Validates the entire chain before issuing the policy

Every step is logged, every decision is auditable, every LLM call is costed and attributed.

## Architecture

```
pipeline/                       Platform agents run across the entire flow:
├── document_ingestion_agent     src/qbe_underwriting/platform/orchestration/     (LangGraph state machine)
├── claims_history_agent         src/qbe_underwriting/platform/governance_agent/  (final validation)
├── hazard_evaluation_agent      src/qbe_underwriting/platform/compliance_agent/  (APRA, RBNZ/FMA)
├── underwriting_risk_agent      src/qbe_underwriting/platform/security/          (prompt injection defence)
├── human_in_the_loop            src/qbe_underwriting/platform/cost_tracking/     (LLM cost attribution)
└── pricing_agent                src/qbe_underwriting/platform/observability/     (audit trail, tracing)
```

See [docs/architecture/end-to-end-flow.md](docs/architecture/end-to-end-flow.md) for the full flow diagram including loopbacks.

## Tech Stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph |
| LLM | Claude (Anthropic SDK) |
| API | FastAPI + Pydantic v2 |
| Database | PostgreSQL 17 + pgvector |
| Caching | Redis |
| OCR | Azure Document Intelligence |
| Observability | OpenTelemetry + structlog + Azure Monitor |
| Dashboard | Streamlit |
| Infrastructure | Docker Compose → Azure Container Apps |

## Quick Start

**Prerequisites:** Docker Desktop, Python 3.12+, `uv`

```bash
# 1. Clone
git clone https://github.com/rajkumar611/AI_UNDERWRITING_SYSTEMS.git
cd AI_UNDERWRITING_SYSTEMS

# 2. Configure
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY and AZURE_DOCUMENT_INTELLIGENCE keys

# 3. Start infrastructure
docker compose up postgres redis -d

# 4. Install dependencies
uv sync

# 5. Run database migrations
uv run alembic upgrade head

# 6. Start the API
uv run uvicorn main:app --reload

# 7. Start the cost dashboard (separate terminal)
uv run streamlit run src/qbe_underwriting/platform/cost_tracking/dashboard.py
```

API docs available at: http://localhost:8000/docs  
Cost dashboard at: http://localhost:8501

## Project Structure

```
AI_UNDERWRITING_SYSTEMS/
├── CLAUDE.md                    ← Claude Code session guide
├── README.md                    ← this file
├── pyproject.toml               ← dependencies and tooling config
├── docker-compose.yml           ← local dev infrastructure
├── .env.example                 ← environment variable template
│
├── docs/
│   ├── architecture/            ← system design and flow diagrams
│   └── Q&A/                     ← interview Q&A for every component (01–14)
│
├── prompts/                     ← versioned LLM system prompts
│   └── <agent-name>/v1.0.md
│
├── pipeline/                    ← underwriting business flow (sequential)
│   ├── document_ingestion_agent/
│   ├── claims_history_agent/
│   ├── hazard_evaluation_agent/
│   ├── underwriting_risk_agent/
│   ├── human_in_the_loop/
│   └── pricing_agent/
│
└── src/qbe_underwriting/platform/                    ← cross-cutting infrastructure
    ├── orchestration/           ← LangGraph workflow engine
    ├── governance_agent/        ← final validation gate
    ├── compliance_agent/        ← APAC regulatory rules
    ├── security/                ← prompt injection prevention
    ├── cost_tracking/           ← LLM cost attribution + dashboard
    └── observability/           ← audit trail, tracing, alerting
```

## Interview Q&A

Detailed Q&A for every component lives in [docs/Q&A/](docs/Q&A/). These cover architecture decisions, security design, regulatory compliance, and production considerations — written at senior engineering level.

## Key Design Decisions

- **Broker documents are untrusted** — sanitised at ingestion before reaching any agent
- **Claims history and hazard run in parallel** — neither depends on the other
- **Pricing only after human review** — never on an unconfirmed risk assessment  
- **Conflict resolution is deterministic** — never left to the LLM to decide
- **Every LLM call is costed and attributed** — to policy ID, agent, and feature
- **Audit trail is append-only and tamper-evident** — regulatory-grade evidence
