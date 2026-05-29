# Pricing Agent — Interview Q&A

Calculates the premium based on a confirmed, human-approved risk decision.
Runs only after human-in-the-loop — never on an unconfirmed risk assessment.

> **Implemented in:** `src/underwriting/pipeline/pricing_agent/`

---

## Q1: Why does pricing run after human review, not before?

**Answer:**

Because pricing must be based on a **finalised** risk decision. If an underwriter overrides the AI's risk score or adds conditions (e.g., "insure but exclude flood"), pricing must reflect those changes — not the original AI output.

Running pricing before human review creates two problems:
1. **Re-run cost** — every underwriter override requires re-running the pricing agent, wasting LLM calls
2. **Consistency risk** — if pricing runs before review, there's a window where a price exists but the risk decision hasn't been confirmed. A bug could issue a policy on an unreviewed risk.

Pricing after review means the inputs are clean, final, and signed off. One run, correct output.

---

## Q2: How does the agent calculate a premium?

**Answer:**

Premium calculation follows a structured build-up:

```
Base Premium  = sum_insured × base_rate (from actuarial tables, by class + risk score band)
    + Risk Loading    (for each specific risk factor — flood, fire, claims history)
    + Claims Loading  (for adverse claims history — scaled to frequency and severity)
    − Security Discount  (sprinklers, alarm systems, security guard)
    − No Claims Discount (clean history over defined period)
──────────────────────────────────────────────────────
= Final Premium
```

Each loading and discount is itemised separately in the output — not collapsed into a single number. This means an underwriter or broker can see exactly what drove the premium and challenge any component.

The actuarial table version used is recorded with every pricing output — so if tables are updated, old policies can be traced back to the version that priced them.

---

## Q3: What inputs does the pricing agent receive?

**Answer:**

Three structured inputs, all required:

| Input | Source | Key fields used |
|---|---|---|
| `RiskAssessment` | `src/underwriting/pipeline/underwriting_risk_agent/` | `risk_score`, `primary_risk_factors`, `mitigating_factors` |
| `UnderwriterDecision` | `src/underwriting/pipeline/human_in_the_loop/` | `override_risk_score`, `conditions`, `exclusions` |
| `MarketRateData` | Injected at runtime by orchestrator | Base rates, loading factors, discount schedules |

If the underwriter overrode the risk score, the agent prices against the **overridden score** — not the original AI score. The original is preserved in the audit trail but does not affect pricing.

---

## Q4: How do you handle currency and multi-jurisdiction pricing?

**Answer:**

All monetary values flow through the system in their original currency — the pricing agent does not convert. The `sum_insured_currency` from the submission data determines the output currency.

Actuarial tables are jurisdiction-specific:
- NZ risks use NZD rates calibrated to NZ loss experience and RBNZ minimum premium requirements
- AU risks use AUD rates calibrated to AU loss experience and APRA minimum premium floors

For multi-location risks (e.g., a fleet insured across AU and NZ), the orchestrator splits the submission into jurisdiction-specific sub-risks, prices each independently, and aggregates. This is flagged as `pricing_method: SPLIT_JURISDICTION` in the output.

---

## Q5: What triggers a loopback from pricing back to human review?

> **Implemented in:** `src/underwriting/platform/orchestration/`, `src/underwriting/pipeline/human_in_the_loop/`

**Answer:**

Two scenarios trigger a loopback from pricing back to the underwriter:

**1. Premium exceeds maximum rate for this class**
If the calculated premium is above the maximum rate defined in underwriting guidelines (can happen when multiple loadings stack), the pricing agent returns a `PREMIUM_CEILING_BREACH` flag. The orchestrator routes back to the underwriter — they must explicitly approve the exceptional premium or adjust coverage terms.

**2. Coverage terms changed after pricing started**
If the underwriter sends back modified conditions mid-pricing (e.g., they initially approved but then added a flood exclusion that significantly changes the risk profile), pricing re-runs against the updated inputs and the underwriter sees the revised premium before final sign-off.

The loopback is always initiated by the orchestrator — the pricing agent itself just returns its output. It never calls the human-in-the-loop component directly.
