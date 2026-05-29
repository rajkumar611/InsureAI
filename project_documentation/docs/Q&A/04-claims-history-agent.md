# Claims History Agent — Interview Q&A

This agent retrieves and analyses a customer's past claims — from internal databases and external sources.
It uses RAG (Retrieval-Augmented Generation) to ground the underwriting decision in real historical data.

> **Implemented across:** `03-claims-history-agent/` (RAG pipeline, retrieval, profile generation)

---

## Q1: Why does claims history need its own dedicated agent?

> **Implemented in:** `03-claims-history-agent/`

**Answer:**

Claims history is one of the most important signals in underwriting — a customer with 5 flood claims in 3 years is a fundamentally different risk to one with a clean 10-year record. But retrieving and making sense of that history is genuinely complex:

- Data lives in **multiple systems** — internal claims management system, industry loss databases (e.g., ICA in Australia, ICNZ in NZ), reinsurance records
- Records need **normalisation** — different systems use different codes, currencies, and date formats
- The data needs **interpretation** — frequency and severity matter differently depending on the class of business and the cause of loss
- It runs **in parallel** with hazard evaluation — neither depends on the other, so running them together saves time

A dedicated agent means this complexity is isolated, testable, and independently updatable. If we get a new data feed from an industry database, we update this one agent — nothing else changes.

---

## Q2: This sounds like a RAG use case — how exactly does RAG work here?

> **Implemented in:** `03-claims-history-agent/` (vector store, retrieval pipeline, LLM synthesis)

**Answer:**

Yes — this is a textbook RAG use case, but applied to structured insurance data rather than documents.

**How it works:**

1. **Indexing (done upfront, not per-request)**  
   Past claims records are pre-processed and stored in a vector database (e.g., Pinecone or pgvector in PostgreSQL). Each record is embedded — converted into a numeric representation the system can search by similarity.

2. **Retrieval (per submission)**  
   When a new submission arrives, the agent searches the vector store for claims matching:
   - Same customer / policy holder
   - Same property address or location region
   - Same class of business
   - Similar risk profile (construction type, occupancy, sum insured range)

3. **Synthesis (LLM step)**  
   The retrieved claims records are passed to an LLM that produces a structured **ClaimProfile**:
   - Total claims in last 3 years / 5 years
   - Largest single loss
   - Most common cause of loss
   - Trend (increasing, stable, decreasing frequency)
   - Risk flag if any single loss exceeds a defined threshold

**Why RAG instead of a direct database query?**  
A SQL query can find exact customer matches. RAG finds *similar* risk profiles — useful when the customer is new but the property address or region has a known loss history. Both are used: SQL for exact match, RAG for contextual enrichment.

---

## Q3: What if the customer has no claims history — they're brand new?

> **Implemented in:** `03-claims-history-agent/` (new customer handling, regional benchmarks)

**Answer:**

No history doesn't mean no signal — it means we use **portfolio and regional benchmarks** instead.

For a new customer, the agent returns:
- **Regional loss statistics** — average claim frequency for this property type in this postcode/region
- **Industry benchmarks** — sector-level loss ratios for this class of business
- **Portfolio comparables** — similar risks from the insurer's own book that can serve as a proxy

The ClaimProfile output in this case is clearly flagged as `source: BENCHMARK` rather than `source: CUSTOMER_HISTORY`. The underwriting risk agent treats benchmark-sourced profiles with higher uncertainty — it widens the confidence interval on the risk score and is more likely to refer the case for human review.

**The principle:** Absence of history is itself a data point — handle it explicitly, not as a missing value.

---

## Q4: How do you handle sensitive customer data in this agent?

> **Implemented in:** `03-claims-history-agent/` (data access controls), `09-security-prompt-injection/` (PII handling), `12-regulatory-compliance_agent/` (data privacy rules)

**Answer:**

Claims data is among the most sensitive data in an insurance business — it contains personal details, loss circumstances, medical information (in some lines), and financial records.

Four protections:

**1. Minimum necessary access**  
The agent only retrieves what it needs for the underwriting decision. It doesn't pull full claim files — it pulls aggregated statistics and flagged events. Raw claim narratives are not passed to the LLM unless specifically needed.

**2. PII stripping before LLM calls**  
Before any claims data enters a prompt, a PII detection layer strips or masks: names, addresses (replaced with region code), NHI/tax numbers, and bank details. The LLM reasons about the *pattern* of claims, not about the individual's personal details.

**3. Data residency compliance**  
In NZ and Australia, insurance data has residency requirements. The vector store and retrieval infrastructure is hosted in the appropriate region — not defaulting to US-based cloud regions.

**4. Audit log on every retrieval**  
Every data access is logged: who (which workflow/agent), what (which records), when. This is required for privacy regulation compliance (Privacy Act NZ, Australian Privacy Act).

---

## Q5: How does the claims history output flow into the underwriting risk agent?

> **Implemented in:** `03-claims-history-agent/` (output schema), `05-underwriting-risk-agent/` (input consumption)

**Answer:**

The agent outputs a typed `ClaimProfile` object — a strict Pydantic schema:

```python
class ClaimProfile(BaseModel):
    customer_id: str
    source: Literal["CUSTOMER_HISTORY", "BENCHMARK", "PARTIAL"]
    total_claims_3yr: int
    total_claims_5yr: int
    largest_single_loss: Decimal
    largest_loss_cause: str
    claim_frequency_trend: Literal["INCREASING", "STABLE", "DECREASING", "INSUFFICIENT_DATA"]
    risk_flags: list[str]           # e.g., ["REPEAT_FLOOD", "LARGE_LOSS_LAST_12M"]
    confidence: float               # 0.0–1.0
    data_quality: Literal["HIGH", "MEDIUM", "LOW"]
```

The Underwriting Risk Agent consumes this alongside the HazardScore from the Hazard Evaluation Agent. Both are required inputs — if either is missing or below minimum quality, the underwriting agent will not produce a risk decision. It raises an `InsufficientDataError` and the orchestrator either retries or escalates.

**Why a strict schema?**  
Because the Underwriting Risk Agent cannot be allowed to reason about free-text claims summaries — that's a hallucination risk. Structured input = predictable, auditable reasoning.
