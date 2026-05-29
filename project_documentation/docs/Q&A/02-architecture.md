# Architecture Interview Q&A — AI Underwriting System

Deep questions on system design, agent boundaries, and technical decisions.

> **How to use:** Each answer is written to be understood by both technical and non-technical interviewers.  
> The `> Implemented in:` line tells you exactly where to find the code on GitHub.

---

## Q1: Walk me through your overall system architecture.

> **Implemented in:** `docs/architecture/` (diagrams and design docs), `src/underwriting/platform/orchestration/` (orchestrator code)

**Answer:**

Think of it like a hospital. There's a **triage nurse (Orchestrator)** who receives every patient (policy request) and decides who they need to see. The patient then visits specialist doctors — a **Pricing Specialist**, a **Hazard Specialist**, a **Compliance Specialist**. Before any decision is finalised, a **Senior Reviewer (Governance Agent)** signs off. If something is too risky or unclear, it's escalated to a **human underwriter**.

In technical terms:

```
[API Gateway]            ← front door, handles auth and rate limiting
      ↓
[Orchestrator]           ← traffic controller; owns the workflow, not the decisions
      ↓ sends tasks to ↓
  [Pricing Agent]        ← calculates premium based on risk profile
  [Hazard Agent]         ← evaluates property/environmental risk
  [Compliance Agent]     ← checks against APAC regulatory rules
  [Governance Agent]     ← validates ALL outputs before they're accepted
      ↓
[Human Escalation]       ← triggered when confidence is low or risk is high
      ↓
[Cost Tracking]          ← records every LLM call's token usage and cost
      ↓
[Observability / Logs]   ← full audit trail of every decision made
```

**Key point:** The Orchestrator never makes underwriting decisions — it only manages flow. This means you can change any agent without touching the others.

---

## Q2: How did you decide where one agent ends and another begins?

> **Implemented in:** `docs/architecture/` (agent boundary design doc), each agent folder in `pipeline/` and `src/underwriting/platform/`

**Answer:**

Three simple rules guided every boundary decision:

**1. Does it use different data?**  
Pricing reads actuarial tables and market rates. Hazard reads property databases and weather risk data. Compliance reads legal rulebooks. When agents need completely different data sources, they should be separate — mixing them creates a fragile, hard-to-maintain mess.

**2. Does it change at a different pace?**  
Regulatory rules update quarterly. Pricing models update monthly when new loss data comes in. Hazard models update after major loss events (floods, earthquakes). If they're one big agent, updating one part risks breaking another. Separate agents = independent deployments.

**3. Can you point to exactly who made which decision?**  
Regulators in Australia (APRA) and New Zealand (RBNZ/FMA) need to know *which part of the system* decided to decline or price a risk. If everything is one agent, you can't answer that. Separate agents give clean, attributable audit trails.

---

## Q3: What happens if two agents disagree with each other?

> **Implemented in:** `src/underwriting/platform/governance_agent/` (conflict resolution rules), `src/underwriting/pipeline/human_in_the_loop/` (escalation), `src/underwriting/platform/observability/` (conflict logging)

**Answer:**

Conflicts are expected — that's why the Governance Agent exists. It has explicit rules for every conflict scenario:

- **Pricing Agent says low risk, Hazard Agent says high risk** → if the gap exceeds a defined threshold, it's escalated to a human underwriter. The system doesn't guess.
- **Compliance Agent flags something that Pricing already approved** → Compliance always wins. Regulatory rules override business logic, no exceptions.
- **Any conflict** → both agent outputs are logged side by side for full auditability.

The important thing: **conflict resolution is never left to the LLM to decide**. It's deterministic, rule-based logic. An LLM deciding how to resolve its own conflict is a governance risk.

---

## Q4: Why did you choose this tech stack?

> **Implemented in:** all folders (stack is consistent throughout the project)

**Answer:**

Every choice was made for a production reason, not because it was the tutorial default:

| Technology | Why chosen |
|---|---|
| **Python** | Best ecosystem for LLM tooling — Anthropic SDK, LangGraph, Pydantic all first-class |
| **FastAPI** | Async-native API framework; auto-generates OpenAPI docs; Pydantic built in |
| **Claude (Anthropic)** | Best instruction-following for structured JSON output; strongest safety defaults for enterprise |
| **PostgreSQL** | Workflow state and cost ledger need ACID guarantees — financial data can't be lost or duplicated |
| **Redis** | Caches agent results so a retry doesn't re-run an already-completed (and costly) agent call |
| **Pydantic models** | Every agent input and output has a strict schema — no free text floating through the system |

The one thing I'd change at real insurer scale: replace direct Anthropic API calls with an **LLM Gateway** for enterprise SLA, data residency compliance, and centralised key management.

---

## Q5: How does the system handle high load — say, 500 policy requests at once?

> **Implemented in:** `src/underwriting/platform/orchestration/` (async design, stateless orchestrator), `src/underwriting/platform/cost_tracking/` (rate limit management)

**Answer:**

Three design decisions make this work:

**1. The Orchestrator is stateless.**  
All workflow state (which agents have run, what they returned) is stored in PostgreSQL — not in memory. This means you can run 10 Orchestrator instances in parallel and they all share the same state. Scale horizontally by adding more instances.

**2. Agent calls are non-blocking (async).**  
A policy workflow doesn't sit and wait for the Pricing Agent to finish before calling the Hazard Agent. Where agents can run in parallel, they do. This cuts end-to-end latency significantly.

**3. LLM rate limits are managed centrally.**  
The real bottleneck in any LLM system isn't your servers — it's the API rate limits. The cost tracking middleware implements a token bucket that distributes LLM capacity fairly across concurrent workflows, rather than letting some workflows starve others.

Batch jobs (like re-pricing an entire portfolio) are separated from the real-time API path entirely, so they never compete with live requests.

---

## Q6: How do you manage prompt changes without breaking things?

> **Implemented in:** `docs/architecture/` (prompt versioning design), `src/underwriting/platform/observability/` (prompt version in audit logs)

**Answer:**

Prompts are treated exactly like code — they are versioned, tested, and reviewed before deployment.

Each prompt template has:
- A **version number** (e.g., `pricing-v2.1`)
- A **changelog** explaining what changed and why
- A **test suite** — fixed input scenarios with expected structured outputs, run automatically on every change

When a prompt is updated, the old version is kept. Every LLM call records which prompt version was used. This means if a new prompt version suddenly increases costs or degrades output quality, you can pinpoint exactly when it changed and roll back.

Think of it as Git for prompts — but with automated tests.

---

## Q7: What would need to change to take this to full production at the insurer?

> **Implemented in:** `docs/architecture/` (production readiness notes), `src/underwriting/platform/security/` (pen test harness)

**Answer:**

This project is built to production *standards* — the architecture, patterns, and security thinking are all production-grade. But a few things would need to be added for actual insurer-scale deployment:

| Gap | What's needed |
|---|---|
| **LLM access** | Replace direct Anthropic API with an enterprise LLM Gateway (Azure OpenAI or private proxy) for SLA, data residency, and key rotation |
| **PII handling** | Add PII detection layer — strip or mask customer data before it enters any prompt |
| **Model fallback** | If Claude is unavailable, route to a secondary model with graceful quality degradation |
| **Finance reporting** | Move cost ledger from PostgreSQL to a data warehouse (Synapse/BigQuery) for finance-grade reporting |
| **Prompt deployments** | Add canary deployments for prompt changes — test new prompt on 5% of traffic before full rollout |
| **Security sign-off** | Formal penetration test of the prompt injection surface by a security team |

The architecture supports all of these additions without structural changes — they're operational upgrades, not redesigns.
