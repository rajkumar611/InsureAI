# Compliance Agent — Interview Q&A

Checks that underwriting decisions and pricing comply with regulatory requirements
for the insurer's operating jurisdictions: New Zealand (RBNZ/FMA) and Australia (APRA).

> **Implemented in:** `src/underwriting/platform/compliance_agent/`

---

## Q1: What regulations does this agent check against?

**Answer:**

The agent covers two regulatory frameworks — one for each jurisdiction the insurer operates in:

| Regulator | Jurisdiction | Key requirements covered |
|---|---|---|
| **APRA** (Australian Prudential Regulation Authority) | Australia | GPS 110 (capital adequacy), GPS 116 (reinsurance), flood cover default inclusion, Target Market Determination (TMD) |
| **RBNZ / FMA** (Reserve Bank NZ / Financial Markets Authority) | New Zealand | Insurance (Prudential Supervision) Act 2010, EQC levy collection, natural hazard disclosure, high-value sign-off thresholds |

Regulations are **not hardcoded** into the agent prompt. They are injected at runtime as `ACTIVE_REGULATIONS` — a structured JSON array loaded from the versioned regulations table in PostgreSQL. When APRA or RBNZ issues updated guidance, the regulations table is updated; the prompt does not change.

---

## Q2: How does the agent handle minimum premium requirements?

**Answer:**

Some classes of business in some jurisdictions have regulatory minimum premiums — the insurer cannot charge below a floor rate regardless of risk score.

The compliance agent checks `pricing_output.final_premium` against the applicable minimum for that jurisdiction and class. Three outcomes:

- **Above minimum** → `minimum_premium_check: PASS`
- **Below minimum** → `minimum_premium_check: FAIL` with severity `BLOCKING` — governance will REJECT the policy
- **Minimum not defined for this jurisdiction/class** → `minimum_premium_check: NOT_APPLICABLE` — logged but not blocking

The minimum premium values come from the injected `ACTIVE_REGULATIONS` data — not from the prompt. If the regulator updates the floor, the regulations table is updated and the new value applies immediately to all new submissions.

---

## Q3: What is a delegated authority limit and how is it enforced?

**Answer:**

Delegated authority is an insurance industry concept: underwriters are authorised to approve risks up to a defined limit without requiring sign-off from a more senior authority. Above that limit, escalation is required.

Typical delegated authority structure:
- Junior underwriter: up to $2M sum insured
- Senior underwriter: up to $10M sum insured
- Underwriting manager: up to $50M sum insured
- Above $50M: requires reinsurance notification and committee approval

The compliance agent checks:
- What is the sum insured for this submission?
- What is the reviewing underwriter's authority level?
- Does the approval exceed their authority?

If it does, the compliance check returns a BLOCKING failure: `DELEGATED_AUTHORITY_EXCEEDED`. The governance agent will reject issuance. The workflow routes to the appropriate authority level for re-approval.

This check cannot be bypassed — it's not advisory. A policy cannot be issued at a sum insured above the approving underwriter's authority, period.

---

## Q4: How do you keep the regulations current without redeploying the system?

**Answer:**

This is a key architectural decision. Regulations change frequently — APRA updates standards, RBNZ changes requirements. If regulations were hardcoded in the prompt or the code, every change would require a code deployment, testing, and release cycle.

Instead, regulations are stored in a **versioned regulations table** in PostgreSQL:

```
regulations
├── id
├── regulator       (APRA | RBNZ | FMA)
├── jurisdiction    (AU | NZ)
├── class_of_business
├── rule_code       (e.g., APRA-PROP-002)
├── rule_description
├── effective_date
├── expiry_date     (null = currently active)
├── rule_data       (JSON — actual values, thresholds, requirements)
└── version
```

At runtime, the orchestrator queries this table for active regulations matching the submission's jurisdiction and class of business. The result is passed to the compliance agent as `ACTIVE_REGULATIONS`.

When a regulation changes:
1. A new row is inserted with the new `effective_date`
2. The old row gets an `expiry_date`
3. No code change, no prompt change, no deployment

The compliance agent always works with current regulations — automatically. Historical submissions can be re-checked against the regulations that were active at their processing date by querying with a historical timestamp.

---

## Q5: How does the agent handle AI decision transparency requirements?

**Answer:**

Both APRA and RBNZ/FMA are progressively tightening requirements on AI use in financial services. The key requirement relevant to this system: **AI-assisted decisions must be explainable**.

An insurer cannot simply say "the model declined this risk." They must be able to explain:
- What factors drove the decision
- What data was used
- Whether human review was involved
- How conflicting signals were resolved

The compliance agent checks:
- Is `decision_rationale` populated in the risk assessment? (Required for any AI-assisted decision)
- If the underwriter overrode the AI, is `override_reason` documented? (Regulators expect human oversight to be documented, not just performed)
- Are the factors in `primary_risk_factors` traceable to input data? (Hallucinated rationale is not compliant)

**Why this matters for the insurer:** RBNZ under the Insurance (Prudential Supervision) Act 2010 and APRA under CPS 220 both require insurers to have robust governance around automated decision-making. An enterprise system without documented AI rationale would fail a regulatory audit.
