# Orchestration — Interview Q&A

The orchestrator is the workflow engine — it owns the state machine, manages agent routing,
handles retries, and controls all loopbacks. Built with LangGraph.

> **Implemented in:** `src/underwriting/platform/orchestration/`

---

## Q1: Why LangGraph specifically for orchestration?

**Answer:**

LangGraph is purpose-built for exactly what this system needs. The alternatives and why they fall short:

| Option | Problem |
|---|---|
| Plain Python functions | No built-in state persistence — workflow fails on restart |
| LangChain chains | Linear only — can't model conditional routing or loopbacks |
| Custom state machine | Significant engineering effort to rebuild what LangGraph gives for free |
| Celery/task queues | Good for simple tasks, not for complex multi-step workflows with shared state |

LangGraph specifically provides:

- **Stateful graph execution** — workflow state persists between steps; resumable after failure
- **Conditional edges** — routing decisions based on agent output (e.g., REFER → human review)
- **Native human-in-the-loop interrupts** — workflow can pause at a node and wait for human input before resuming
- **Checkpointing** — saves the complete state after every node; if the process crashes, resume from the last checkpoint
- **Parallel node execution** — steps 02 and 03 run simultaneously without extra plumbing

These are not afterthoughts — they're core LangGraph features that map directly to this system's requirements.

---

## Q2: How does the state machine work in practice?

**Answer:**

Each policy submission becomes a **graph execution** with a typed state object:

```python
class WorkflowState(TypedDict):
    submission_id: str
    policy_id: str
    submission_data: SubmissionData | None
    claim_profile: ClaimProfile | None
    hazard_score: HazardScore | None
    risk_assessment: RiskAssessment | None
    underwriter_decision: UnderwriterDecision | None
    pricing_output: PricingOutput | None
    compliance_result: ComplianceResult | None
    governance_decision: GovernanceDecision | None
    workflow_status: WorkflowStatus
    error_log: list[WorkflowError]
```

The graph nodes are the pipeline agents. The edges between them define routing:
- After document ingestion → always go to orchestrator (parallel launch of 02 and 03)
- After risk assessment → conditional: ACCEPT/DECLINE goes to human review; low confidence also goes to human review
- After human review → DECLINE ends the workflow; APPROVE/OVERRIDE proceeds to pricing

State is persisted to PostgreSQL after every node completion. If the process restarts, LangGraph reloads the state and resumes from the last completed node — no work is repeated.

---

## Q3: How does the orchestrator handle retries?

**Answer:**

Retries are handled at the node level with an exponential backoff strategy:

| Failure type | Retry behaviour |
|---|---|
| Transient (timeout, rate limit) | Retry with backoff: 1s → 2s → 4s. Max 3 attempts. |
| Schema validation failure | Retry once with the error message appended to the prompt — gives the agent context on what went wrong |
| Persistent failure (3 attempts exhausted) | Pause workflow, set `workflow_status: FAILED`, raise alert |

**What "pause" means in practice:**
The state is saved to PostgreSQL with the failure details. An alert is raised to the operations team. A human can investigate and either restart the workflow from the failed node or mark it for manual processing. Nothing is silently dropped.

The key guarantee: **every failure is visible and recoverable**. The system never silently moves past a failed agent call.

---

## Q4: The system has loopbacks — how does the orchestrator prevent infinite loops?

**Answer:**

Every loopback path has a maximum iteration count, enforced by the orchestrator:

| Loopback | Max iterations | What happens at limit |
|---|---|---|
| Document ingestion re-request | 3 | Workflow paused — broker coordinator notified |
| Claims history re-query | 2 | Proceeds with available data, flagged LOW quality |
| Hazard evaluation re-query | 2 | Proceeds with available data, flagged LOW confidence |
| Pricing → human re-approval | 3 | Escalated to senior underwriter |

Each iteration is counted and stored in the workflow state. The orchestrator checks the count before routing — it never routes a loopback if the limit is reached.

Additionally, every loopback is logged with a reason. If a workflow loops more than once on the same path, the operations team is notified — repeated looping usually indicates a data quality problem upstream.

---

## Q5: How does the orchestrator assign policy IDs and ensure uniqueness?

**Answer:**

Policy IDs are assigned at the point the orchestrator takes control — after document ingestion completes successfully. Two-part design:

**1. Workflow ID (internal)**
Assigned immediately on submission receipt — before document ingestion. Used to track the entire lifecycle including failed or rejected submissions. Format: `WF-{timestamp}-{uuid4_short}`.

**2. Policy ID (business-facing)**
Assigned only after the orchestrator confirms the submission is processable (document ingestion succeeded, class of business confirmed). Format: `POL-{year}-{sequential_number}`. Sequential numbers are generated using PostgreSQL sequences — atomic, no duplicates, no gaps.

Policy ID is propagated through every subsequent agent call and every LLM cost tracking record. This is how the finance dashboard can show cost-per-policy — every token is tagged with the policy ID from the moment it's assigned.
