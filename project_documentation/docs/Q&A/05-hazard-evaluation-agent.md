# Hazard Evaluation Agent — Interview Q&A

This agent assesses the physical and environmental risk of a property.
It runs in parallel with the claims history agent — both feed into the underwriting risk agent.

> **Implemented in:** `src/underwriting/pipeline/hazard_evaluation_agent/`

---

## Q1: What hazards does this agent evaluate?

**Answer:**

Four dimensions, each scored independently:

| Hazard | What it covers |
|---|---|
| **Flood** | Proximity to flood plains, historical flood frequency, drainage infrastructure, coastal/river exposure |
| **Fire** | Bushfire zones (AU/NZ), urban fire risk, proximity to fire stations, construction material flammability |
| **Structural** | Building age, construction type, seismic zone (NZ is highly seismic), known ground subsidence |
| **Environmental** | Proximity to industrial sites, contaminated land registers, coastal erosion, extreme weather exposure |

Each dimension returns `EXTREME | HIGH | MEDIUM | LOW | NEGLIGIBLE` plus a one-sentence rationale. The overall hazard level is a synthesised judgement — not a simple average. A property with EXTREME flood risk is HIGH overall even if all other dimensions are LOW.

---

## Q2: Where does the external hazard data come from?

**Answer:**

External hazard data is injected into the agent at runtime — the agent never calls external APIs itself. The orchestrator fetches hazard data before invoking the agent, then passes it as a structured JSON payload. This is intentional:

- The exact data used in a decision is **logged with the decision** — reproducible at audit time
- API rate limits and retries are managed centrally by the orchestrator
- External calls are easy to mock in tests — no live API dependency during CI

| Region | Source | Data |
|---|---|---|
| New Zealand | LINZ, NIWA | Flood zones, seismic risk, coastal erosion |
| Australia | Geoscience Australia, BOM | Flood mapping, bushfire prone land |

If data is unavailable for a dimension, the agent defaults to `MEDIUM` and adds the dimension to `data_gaps` — conservative, never optimistic.

---

## Q3: How does construction type affect the hazard score?

**Answer:**

Construction type primarily affects **fire risk** and **structural risk**:

| Construction | Fire risk impact | Structural risk impact |
|---|---|---|
| Timber frame | Increases significantly | Moderate (age-dependent) |
| Brick/masonry | Reduces | Low |
| Concrete | Reduces significantly | Low |
| Steel frame | Neutral | Low (modern) |
| Unknown | Flagged as uncertain | Defaults to MEDIUM |

For seismic risk in New Zealand, pre-1976 buildings receive elevated structural risk regardless of material — that's when NZ building codes were significantly strengthened following historic earthquake lessons.

---

## Q4: What happens when hazard data is missing or low quality?

**Answer:**

Missing or incomplete data is handled conservatively and always made visible:

- **Missing dimension data** → defaults to `MEDIUM`, added to `data_gaps`
- **Outdated data** → `confidence` score reduced, noted in output
- **No external data at all** → `overall_hazard_level` forced to `HIGH`, flagged for manual review

The `confidence` score (0.0–1.0) propagates to the underwriting risk agent, which treats low-confidence hazard inputs with higher uncertainty — making a REFER decision more likely. The principle: when uncertain, assume more risk not less.

---

## Q5: How do this agent's outputs combine with claims history?

> **Implemented in:** `src/underwriting/pipeline/underwriting_risk_agent/`

**Answer:**

Both agents run simultaneously and independently. The underwriting risk agent waits for both outputs before starting. The combination is a reasoned synthesis, not a formula.

**Conflict example — LOW hazard + HIGH claims frequency:**
Unusual combination. Could mean a recurring maintenance issue (burst pipes, roof leaks) not captured in environmental data. The risk agent flags `signal_conflict: true` and either resolves it with a clear rationale or refers to a human.

**Conflict example — EXTREME hazard + zero claims history:**
Could mean the property is new, or recently moved to a high-risk area. The risk agent notes the lack of historical validation and widens its uncertainty interval — more likely to REFER.

Neither agent's output overrides the other. The underwriting risk agent must explain how it weighted both in `decision_rationale`, which is logged and auditable.
