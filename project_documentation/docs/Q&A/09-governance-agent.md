# Governance Agent — Interview Q&A

The final gatekeeper before policy issuance. Sees the entire workflow chain and validates
that all outputs are internally consistent, compliant, and safe to commit.

> **Implemented in:** `src/underwriting/platform/governance_agent/`

---

## Q1: Why does governance sit in src/underwriting/platform/, not pipeline/?

**Answer:**

Because governance is not a business step — it's infrastructure that serves the entire workflow.

Pipeline agents do work: extract documents, retrieve claims, evaluate hazards, price risk. Governance validates that work. It has no business output of its own — its only output is a decision on whether the chain as a whole is valid.

It also runs **after** the pipeline is complete, with sight of all outputs simultaneously. No pipeline agent has that full view. Governance needs the complete picture to do its job — so it belongs at the platform level, not inside the sequential flow.

---

## Q2: What exactly does the governance agent validate?

**Answer:**

Four validation categories, all run before policy issuance:

**1. Consistency check**
Does the pricing make sense given the risk score? A EXTREME-risk property priced at minimum premium is a red flag. Does the underwriter's override have a documented reason? Are policy conditions consistent with the risk flags from claims history and hazard agents?

**2. Completeness check**
Are all required fields populated across every agent output? Is the underwriter decision present and signed off? Are any fields null that cannot be null at policy issuance?

**3. Compliance check**
Are there any violations from the compliance agent? Is the sum insured within delegated authority limits for this class? If the AI decision was overridden, is the override reason documented?

**4. Fraud indicators check**
Does any combination of signals across the full chain raise a fraud concern not already flagged? For example: declared claims differ significantly from retrieved claims, or sum insured is dramatically higher than market value for the property type.

---

## Q3: What happens when governance rejects a workflow?

**Answer:**

A governance rejection (`governance_outcome: REJECTED`) means the policy **cannot be issued**. The workflow stops here.

The rejection is never silent:
- A rejection record is written with specific `rejection_reasons` (each linked to a rule or check)
- The case is returned to the underwriter queue with the rejection reasons visible
- The underwriter can correct the issue and resubmit — or escalate to a senior underwriter
- The rejection itself is logged in the audit trail permanently — even if the case is later corrected and approved

**What governance does NOT do:** It does not fix problems itself. If pricing is inconsistent with risk score, governance flags it and stops — it doesn't recalculate the premium. Each agent owns its output. Governance validates the chain.

---

## Q4: How does governance handle conflicts between agents?

**Answer:**

Conflict resolution follows explicit, deterministic rules — never left to the LLM:

| Conflict | Resolution |
|---|---|
| Pricing Agent says low risk, Hazard Agent says high | Flag consistency failure → REJECTED or REFER_TO_SENIOR_UNDERWRITER |
| Compliance Agent flags a rule violation that Pricing approved | Compliance always wins → REJECTED |
| Underwriter approved a DECLINE recommendation with no override reason | REJECTED — override reason is mandatory |
| Minor inconsistency below threshold | Logged as `governance_notes` — does not block approval |

The threshold for blocking vs. noting is defined in the governance rules configuration — not hardcoded in the prompt. This means thresholds can be adjusted without changing prompt files.

---

## Q5: How does this differ from the compliance agent?

**Answer:**

They have different jobs and run at different points:

| | Compliance Agent | Governance Agent |
|---|---|---|
| **When it runs** | During the pipeline (after risk assessment and pricing) | After the entire pipeline — final gate |
| **What it checks** | Regulatory rules for the specific jurisdiction and class | Internal consistency of the whole workflow chain |
| **Who it reports to** | Its output feeds into governance | Its output is the final issuance decision |
| **Can it block issuance?** | Indirectly — its NON_COMPLIANT status is checked by governance | Directly — REJECTED stops issuance |
| **Scope** | APRA, RBNZ/FMA rules | Pricing logic, completeness, fraud signals, override documentation |

Think of compliance as a specialist advisor (knows the regulations deeply) and governance as the signing authority (has the full picture and makes the final call). Governance reads the compliance report as one of its inputs.
