# Observability & Monitoring — Interview Q&A

Audit trail, decision logs, distributed tracing, and alerting across the entire workflow.
Every state transition is logged. Every decision is reconstructable.

> **Implemented in:** `src/underwriting/platform/observability/`

---

## Q1: What is the difference between logging, tracing, and the audit trail in this system?

**Answer:**

Three distinct observability layers, each with a different purpose:

| Layer | Tool | What it captures | Who uses it |
|---|---|---|---|
| **Structured logging** | structlog → Azure Monitor | Application events, errors, warnings — human-readable with machine-parseable fields | Engineering (debugging) |
| **Distributed tracing** | OpenTelemetry | End-to-end request traces across agents — latency, spans, dependencies | Engineering (performance) |
| **Audit trail** | Append-only PostgreSQL table | Every underwriting decision, with full inputs and outputs — immutable record | Compliance, regulators, legal |

These are different things. Logging tells you what the system did. Tracing tells you how long it took. The audit trail tells you what decisions were made and why — and it must be tamper-proof.

---

## Q2: What is captured in the audit trail for each policy decision?

**Answer:**

The audit trail is a ledger — append-only, never updated, never deleted. For every underwriting workflow, the following records are written:

**Per-agent record:**
- `workflow_id`, `policy_id`, `agent_name`
- `prompt_version` used
- `input_payload` (the structured data sent to the agent)
- `raw_llm_response` (exactly what the model returned, before parsing)
- `parsed_output` (the validated Pydantic object)
- `confidence_score`
- `processing_time_ms`
- `timestamp`

**Per-decision record (risk assessment, human review, governance):**
- Full agent outputs as above, plus:
- `decision_type` (AI_DECISION | HUMAN_OVERRIDE | GOVERNANCE_APPROVAL | GOVERNANCE_REJECTION)
- `decision_value` (ACCEPT | DECLINE | REFER | APPROVED | REJECTED)
- `decision_rationale`
- `underwriter_id` (if human involved)
- `override_reason` (if overridden)

**Why the raw LLM response?**
Because the parsed output alone isn't enough for a regulator. If there's ever a dispute about what the AI "actually said," the raw response is the ground truth. The parsed output is what the system acted on — the raw response is what the model produced.

---

## Q3: How does distributed tracing work across multiple agents?

**Answer:**

Each policy workflow is assigned a `trace_id` at the point of submission. This ID propagates through every agent call — it's included in every OpenTelemetry span created within the workflow.

The result: in Azure Monitor (or any OpenTelemetry-compatible backend), you can search by `trace_id` and see the complete end-to-end execution:

```
Trace: WF-1731234567-a3f2
├── document-ingestion-agent    [1240ms]  ✓
├── claims-history-agent        [2340ms]  ✓  (parallel)
├── hazard-evaluation-agent     [1890ms]  ✓  (parallel)
├── underwriting-risk-agent     [3120ms]  ✓
├── human-in-the-loop           [14400s]  ✓  (human review time)
├── pricing-agent               [1560ms]  ✓
├── compliance_agent            [890ms]   ✓
└── governance_agent            [1230ms]  ✓
Total wall time: ~25s (excluding human review)
```

This makes performance investigation instant — you can see exactly which agent was slow on a specific submission, without guessing.

---

## Q4: What alerts does the system raise and who receives them?

**Answer:**

Alerts are categorised by audience and urgency:

| Alert | Trigger | Recipient | Channel |
|---|---|---|---|
| Workflow failure | Agent fails after 3 retries | Engineering | Slack #ops-alerts |
| Cost anomaly | Workflow cost > 3× p95 baseline | Engineering | Slack #cost-alerts |
| SLA breach | Underwriter review SLA missed | Underwriting manager | Email + dashboard flag |
| Security incident | Canary token in agent output | Security team | PagerDuty (high priority) |
| Governance rejection spike | >5% of workflows rejected in 1 hour | Engineering + compliance | Slack #governance-alerts |
| Compliance failure | NON_COMPLIANT result on any policy | Compliance officer | Email + case queue flag |

Alerts are not just notifications — they link directly to the relevant workflow ID so the recipient can investigate immediately without searching for context.

---

## Q5: How do you ensure the audit trail is tamper-proof?

**Answer:**

Four mechanisms protect audit trail integrity:

**1. Append-only table design**
The audit trail table has no UPDATE or DELETE privileges — only INSERT. This is enforced at the PostgreSQL role level. The application user cannot modify existing records, only add new ones.

**2. Cryptographic hashing**
Each audit record includes a SHA-256 hash of its content, plus the hash of the previous record (chain-of-custody style). Any tampering with a record breaks the chain — detectable immediately.

**3. Separate database credentials**
The audit trail is written using a dedicated database user with INSERT-only permissions on audit tables. The main application user has no access to these tables. Even a compromised application cannot modify the audit trail.

**4. Periodic export to immutable storage**
Daily exports of the audit trail are written to Azure Blob Storage with immutability policies (WORM — Write Once Read Many). Even if the database were compromised, the exported snapshots provide a tamper-evident backup.

**Why this level of protection?**
In regulated financial services, audit trails are legal documents. If a policyholder disputes a declined claim and the matter goes to a regulator or court, the audit trail is evidence. Tampered evidence is worse than no evidence — it implies intent. These protections ensure the audit trail is trustworthy enough to stand up to regulatory scrutiny.
