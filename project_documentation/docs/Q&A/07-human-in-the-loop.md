# Human-in-the-Loop — Interview Q&A

A workflow component, not an LLM agent. The human makes the decision; the system facilitates and records it.
Sits between risk assessment and pricing — a mandatory checkpoint for referred and high-value cases.

> **Implemented in:** `src/underwriting/pipeline/human_in_the_loop/`

---

## Q1: Why is human review a designed pipeline step, not just an exception handler?

**Answer:**

Most AI systems treat human review as a fallback — something that happens when the AI fails. In regulated financial services, that thinking is backwards.

Human review is required by design for specific cases:
- **Delegated authority limits** — policies above a defined value require underwriter sign-off, regardless of AI confidence
- **Referred cases** — legally require a named underwriter decision on record
- **Novel risks** — new construction types, emerging industries, or unusual exposures the AI hasn't been trained on

Making it an explicit pipeline step means it is logged, timed, and auditable like every other step. The orchestrator enforces sequencing — pricing cannot start until human review is complete for cases that require it.

---

## Q2: What does the underwriter see when reviewing a case?

**Answer:**

A structured review pack — not raw agent JSON:

| Section | Content |
|---|---|
| **Summary** | Policy ID, insured name, class of business, sum insured |
| **AI Risk Decision** | Accept/Decline/Refer, risk score (0–1), confidence |
| **AI Rationale** | Plain-English explanation of the decision |
| **Key Risk Factors** | Top factors driving the score up |
| **Mitigating Factors** | Factors that reduced the score |
| **Claims Profile** | Frequency, severity, trend, risk flags |
| **Hazard Summary** | Flood/fire/structural/environmental ratings |
| **Signal Conflicts** | Any agent disagreements, highlighted prominently |
| **Data Quality Warnings** | Low-confidence or missing fields |

The underwriter audits a recommendation, not a blank form — faster and more consistent.

---

## Q3: What actions can an underwriter take, and what happens next?

**Answer:**

| Action | Workflow effect |
|---|---|
| **Approve** | Proceeds to pricing with original AI risk score |
| **Approve with conditions** | Proceeds to pricing — conditions appended to policy terms |
| **Override risk score** | Proceeds to pricing with new score; original AI score preserved for audit |
| **Decline** | Workflow ends — decline notice generated, reason logged |
| **Request more documents** | Loopback to `src/underwriting/pipeline/document_ingestion_agent/` — workflow pauses |
| **Request more claims data** | Loopback to `src/underwriting/pipeline/claims_history_agent/` with targeted query |
| **Escalate to senior** | Reassigned to senior underwriter queue |

Every action requires a mandatory free-text reason — no silent approvals or declines.

---

## Q4: How do you prevent this step from becoming a bottleneck?

**Answer:**

Three mechanisms:

**1. SLA timers with auto-escalation**

| Case type | SLA |
|---|---|
| Standard | 4 business hours |
| Referred | 2 business hours |
| High-value (>$10M) | 1 business hour |

Approaching deadline → reminder. Missed deadline → auto-escalate to senior queue.

**2. Only cases that truly need review reach this step**
Pre-screen rules in the underwriting risk agent handle clear Accept/Decline cases without human involvement. Human review is reserved for genuinely ambiguous or high-value cases.

**3. Concurrent queue with locking**
Multiple underwriters process the queue simultaneously. Cases are locked to prevent duplicate review — unlocked after 15 minutes of inactivity.

---

## Q5: How is a human override recorded for audit and compliance?

> **Implemented in:** `src/underwriting/pipeline/human_in_the_loop/`, `src/underwriting/platform/observability/`

**Answer:**

Overrides are the most scrutinised records in the system — regulators specifically look at whether AI decisions are genuinely reviewed or rubber-stamped.

Every override captures:

| Field | Example |
|---|---|
| `underwriter_id` | UW-00341 |
| `original_ai_decision` | REFER |
| `original_ai_risk_score` | 0.71 |
| `override_decision` | ACCEPT |
| `override_risk_score` | 0.58 |
| `override_reason` | "Property has a recently certified flood barrier. AI had no data on this — confirmed from supplementary broker document." |
| `timestamp` | 2024-11-15T10:42:33Z |

The original AI score is **never deleted** — both the AI decision and the human override exist side by side. This enables model performance monitoring: systematic override patterns signal the AI needs retraining.
