# Underwriting Risk Assessment Agent — Interview Q&A

This is the core decision-making agent. It synthesises everything — document data, claims history,
hazard scores — and produces the risk decision: Accept, Decline, or Refer to a human underwriter.

> **Implemented in:** `05-underwriting-risk-agent/`

---

## Q1: What does this agent actually do — and why is it separate from the other agents?

> **Implemented in:** `05-underwriting-risk-agent/`

**Answer:**

Think of this agent as the **senior underwriter's brain** — the one who takes all the evidence and makes the call.

The agents before it are all specialists:
- Document Ingestion says: "Here's what the broker submitted."
- Claims History says: "Here's what happened to this customer before."
- Hazard Evaluation says: "Here's how risky this property/location is."

None of them make the *underwriting decision*. That's this agent's job — to synthesise all three into a coherent risk assessment:

- **RiskScore** — a 0.0 to 1.0 number representing overall risk
- **RiskDecision** — Accept, Decline, or Refer
- **RiskRationale** — structured explanation of which factors drove the decision
- **ConfidenceScore** — how certain the agent is about its own decision

It's separate because the synthesis logic is different from the specialist logic. If we buried it inside the orchestrator, we'd have no clean place to test it, version it, or explain it to a regulator.

---

## Q2: How does the agent synthesise three different inputs into one risk decision?

> **Implemented in:** `05-underwriting-risk-agent/` (synthesis prompt, weighting logic, output schema)

**Answer:**

The agent receives three structured inputs:

| Input | From |
|---|---|
| `SubmissionData` | 00-document-ingestion-agent |
| `ClaimProfile` | 03-claims-history-agent |
| `HazardScore` | 04-hazard-evaluation-agent |

The synthesis works in two layers:

**Layer 1 — Rule-based pre-screening (deterministic)**  
Before the LLM is involved, hard rules are checked:
- If `HazardScore.flood_zone == "EXTREME"` AND `ClaimProfile.total_claims_3yr > 2` → auto-Refer, no LLM needed
- If `SubmissionData.sum_insured > $50M` → always Refer regardless of risk score (high-value threshold)
- If any `ClaimProfile.risk_flags` contains `"FRAUD_SUSPICION"` → auto-Decline

These rules are fast, cheap (no LLM call), and 100% auditable.

**Layer 2 — LLM risk reasoning (for non-trivial cases)**  
Cases that pass pre-screening are sent to the LLM with all three inputs and a structured reasoning prompt. The LLM produces:
- A weighted assessment of each factor
- An overall risk narrative
- A recommended decision with rationale

The LLM output is validated against a strict `RiskAssessment` Pydantic schema before it leaves the agent.

**Why both layers?**  
Rule-based pre-screening catches obvious cases cheaply and auditably. LLM reasoning handles nuance that rules can't — a property with moderate flood risk but an excellent 15-year claims record might still be a good risk. Rules alone can't make that judgement.

---

## Q3: When does the agent escalate to a human underwriter vs. deciding itself?

> **Implemented in:** `05-underwriting-risk-agent/` (escalation triggers), `06-human-in-the-loop/` (review workflow)

**Answer:**

Escalation is **rule-based, not LLM-based**. The agent never decides "I think I need help" — specific conditions trigger escalation automatically:

| Trigger | Reason |
|---|---|
| `confidence_score < 0.70` | Agent is uncertain — human eyes needed |
| `risk_decision == "REFER"` | By definition requires human review |
| `sum_insured > $10M` | High-value policies always get human sign-off |
| `ClaimProfile.data_quality == "LOW"` | Decision based on poor data → human validates |
| `HazardScore.confidence < 0.65` | Hazard data uncertain → human assesses |
| New customer with no history | No track record → human judgement required |
| Any `FRAUD_SUSPICION` flag | Fraud cases always go to human + compliance team |

**What happens on escalation?**  
The agent still produces its best risk assessment — it doesn't just say "I give up." The human underwriter sees the full agent reasoning, the supporting data, and the confidence score. They're reviewing a recommendation, not starting from scratch. This makes the human's job faster and more informed.

---

## Q4: How do you make the risk decision explainable — not just a number?

> **Implemented in:** `05-underwriting-risk-agent/` (rationale schema), `11-observability-monitoring/` (decision audit trail)

**Answer:**

A risk score of 0.73 means nothing without context. The agent is required to produce a structured rationale alongside every decision:

```python
class RiskRationale(BaseModel):
    primary_risk_factors: list[str]     # ["REPEAT_FLOOD_CLAIMS", "FLOOD_ZONE_HIGH"]
    mitigating_factors: list[str]        # ["15_YEAR_CLEAN_RECORD", "SPRINKLER_SYSTEM"]
    data_quality_notes: list[str]        # ["SUM_INSURED_UNVERIFIED"]
    decision_basis: str                  # human-readable summary
    applicable_guidelines: list[str]    # ["AI_UW_PROPERTY_GUIDE_v4.2", "RBNZ_FLOOD_GUIDANCE_2023"]
```

This means:
- **An underwriter reviewing a Refer decision** sees exactly why the agent referred it — not just a number
- **A regulator asking why a risk was declined** gets a structured, timestamped rationale
- **An audit comparing two similar risks priced differently** can see which factors drove the difference

The decision is never just a score. It's always a score + rationale + confidence + data quality notes.

---

## Q5: How does this agent handle contradictory signals — e.g., excellent claims history but extreme hazard score?

> **Implemented in:** `05-underwriting-risk-agent/` (conflict handling), `08-governance-guardrails-agent/` (cross-validation)

**Answer:**

This is the most common real-world scenario — and the most interesting underwriting problem. A well-run business in a flood-prone area. A brand new property in a historically risky postcode.

The agent handles this explicitly, not by averaging the signals away:

**Step 1 — Conflict detected**  
If `HazardScore.risk_level` and `ClaimProfile` signals point in opposite directions beyond a defined threshold, the agent flags a `SIGNAL_CONFLICT`.

**Step 2 — Weighted reasoning**  
The LLM is prompted to reason about *why* the signals conflict and which is more predictive for this specific risk:
- "Is the good claims history because the customer is genuinely low-risk, or because they haven't been hit by an event yet?"
- "Is the hazard score based on regional data, or property-specific data?"

**Step 3 — Conservative default**  
When signals conflict and the LLM cannot resolve with high confidence, the decision defaults to **Refer** — not Accept. The principle: when uncertain, get a human. Never Accept on ambiguous data.

**Step 4 — Governance validation**  
The Governance Agent independently checks that a conflicting-signal case wasn't auto-Accepted. If it was, Governance overrides and escalates. This is a hard safety net — the Underwriting Agent's output is not the final word.
