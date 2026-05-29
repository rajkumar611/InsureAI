# LLM Cost Tracking — Interview Q&A

Every LLM call in the system is measured, tagged, and stored.
The cost dashboard gives finance teams, management, and engineering full visibility into AI spend.

> **Implemented in:** `src/underwriting/platform/cost_tracking/`

---

## Q1: Why build a custom cost tracking layer instead of using the cloud provider's billing?

**Answer:**

Cloud billing (Azure, AWS, GCP) gives you a monthly total broken down by service. That's useful for accounting but useless for operations:

- It can't tell you which **policy** was expensive
- It can't tell you which **agent** is inefficient
- It can't tell you which **prompt version** caused a cost spike last Tuesday
- It can't tell you the **cost per product line** for the finance team
- It can't alert you when a single workflow costs 10× the average

Custom cost tracking solves all of these. Every LLM call is wrapped by a middleware that captures granular metadata at the point of the call — not aggregated after the fact by a billing system.

The result: LLM spend is managed like any other operational cost — measurable, attributable, forecastable, and alertable.

---

## Q2: What exactly is captured for every LLM call?

**Answer:**

The cost tracking middleware wraps every `client.messages.create()` call and captures:

| Field | Example | Purpose |
|---|---|---|
| `submission_id` | SUB-2024-00821 | Links cost to the submission |
| `policy_id` | POL-2024-00391 | Links cost to the issued policy (if reached) |
| `workflow_id` | WF-1731234567-a3f2 | Links cost to the full workflow run |
| `agent_name` | underwriting-risk-agent | Which agent made the call |
| `prompt_version` | 1.0 | Which prompt version was used |
| `model_id` | claude-sonnet-4-6 | Which model was called |
| `input_tokens` | 1240 | Tokens sent |
| `output_tokens` | 387 | Tokens received |
| `cost_usd` | 0.0048 | Calculated from model pricing |
| `latency_ms` | 2340 | Response time |
| `feature_tag` | hazard-evaluation | Business feature label |
| `timestamp` | 2024-11-15T09:32:14Z | When the call was made |

All records go to an **append-only cost ledger** — records are never updated or deleted, only inserted. This means the cost history is immutable and auditable.

---

## Q3: What does the finance team dashboard show?

**Answer:**

The dashboard (built in Streamlit) gives finance teams answers to the questions they actually ask:

| Finance question | Dashboard view |
|---|---|
| "How much does it cost to issue one policy?" | Average cost per policy, broken down by agent contribution |
| "Is AI spend growing faster than policy volume?" | Cost trend vs. policy volume chart, monthly |
| "Which product line is most expensive?" | Cost by class of business (property vs. liability vs. marine) |
| "Why did costs jump last week?" | Anomaly detection with drill-down to specific workflow IDs |
| "What would it cost to process 5,000 policies/month?" | Per-policy cost × projected volume forecast |
| "Which model is giving us the best value?" | Cost vs. quality comparison across model versions |

The dashboard has two views:
- **Finance view** — monetary cost, policy count, trend, forecast (no technical detail)
- **Engineering view** — cost per agent, token efficiency, latency, prompt version comparison

---

## Q4: How does the system detect a cost anomaly?

**Answer:**

Anomaly detection runs on a rolling 24-hour window using a simple but effective approach:

1. **Baseline** — calculate the p95 cost for each agent over the previous 30 days
2. **Alert threshold** — any single workflow that exceeds 3× the p95 baseline for any agent triggers an alert
3. **Trend alert** — if the rolling 24-hour average cost per policy increases by more than 20% vs. the previous 7-day average, a trend alert is raised

Alerts go to the engineering team (Slack/email). The alert includes:
- Which agent is expensive
- The specific workflow ID (so the engineer can inspect the exact prompt and response)
- The cost vs. baseline comparison

The most common cause of cost anomalies: a prompt change that causes the LLM to produce much longer outputs than expected. The alert + workflow ID lets engineers pinpoint it in minutes, not hours of log trawling.

---

## Q5: How is cost data used to improve the system over time?

**Answer:**

Cost data drives three types of improvement:

**1. Prompt efficiency optimisation**
By comparing cost per agent across prompt versions, engineering can measure whether a new prompt is more or less token-efficient than its predecessor. A prompt that costs 30% less per call without quality degradation is a clear win — the cost data provides the before/after comparison.

**2. Model right-sizing**
Not every agent needs the most capable (and most expensive) model. Cost data reveals which agents have low variance in output (suggesting the task is well-defined and a smaller model might work) vs. high variance (suggesting the task needs reasoning capacity). This informs model selection decisions with data, not intuition.

**3. Finance team trust**
When the finance team can see a clear cost-per-policy metric and watch it stay stable as volume grows, they trust the AI system enough to approve scaling it. Cost transparency is the foundation of that trust. Without it, AI spend is always "scary and unpredictable" — which limits how far leadership will let the system grow.
