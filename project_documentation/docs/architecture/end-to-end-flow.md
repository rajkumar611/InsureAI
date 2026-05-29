# End-to-End Underwriting Flow — AI Underwriting System

## The Real Business Flow

Insurance underwriting starts with a **broker** — not a user typing into a chat box.
A broker submits documents on behalf of their client. Those documents are messy, unstructured,
and come from an untrusted external party. The system must handle that reality.

Agents do not always move forward. Real underwriting involves **loopbacks** — an underwriter
requests more documents, a risk agent needs deeper claims data, pricing needs re-approval after
a coverage change. The orchestrator manages all of these paths.

---

## Flow Diagram (with loopbacks)

```mermaid
flowchart TD
    BROKER(["`**BROKER**
    Submits PDFs, photos,
    claim forms, client details`"])

    S01["`**STEP 01 · Document Ingestion Agent**
    • OCR extracts text from PDFs & images
    • LLM classifies document type & class of business
    • Extracts structured data into validated schema
    ⚠️ PROMPT INJECTION SANITISATION — input is UNTRUSTED`"]

    ORCH["`**ORCHESTRATOR**
    • Assigns Policy ID + Workflow ID
    • Starts LangGraph state machine
    • Fires parallel agent calls`"]

    S02["`**STEP 02 · Claims History Agent**
    RAG over past claims for this
    customer / property / region
    _Output: ClaimProfile_`"]

    S03["`**STEP 03 · Hazard Evaluation Agent**
    Flood, fire, structural &
    environmental risk scoring
    _Output: HazardScore_`"]

    S04["`**STEP 04 · Underwriting Risk Agent**
    • Synthesises docs + claims + hazard
    • Rule-based pre-screen (no LLM)
    • LLM reasoning for non-trivial cases
    _Output: Accept / Decline / Refer_`"]

    S05["`**STEP 05 · Human-in-the-Loop**
    Triggered: REFER, confidence < 0.70,
    high value, new customer, fraud flag
    Underwriter: Approve / Decline / Override`"]

    S06["`**STEP 06 · Pricing Agent**
    • Confirmed risk score as input
    • Calculates premium + terms
    _Output: PricingOutput_`"]

    GOV["`**GOVERNANCE AGENT**
    • Validates entire chain
    • Compliance checks (APRA, RBNZ/FMA)
    • Signs off policy`"]

    POLICY(["`✅ **POLICY ISSUED**`"])

    DECLINE(["`❌ **DECLINED**
    Notice issued to broker`"])

    BROKER --> S01
    S01 -->|Missing docs| BROKER
    S01 --> ORCH
    ORCH --> S02
    ORCH --> S03
    S02 --> S04
    S03 --> S04
    S04 -->|Needs deeper claims| S02
    S04 -->|Needs more hazard detail| S03
    S04 --> S05
    S05 -->|Request more documents| S01
    S05 -->|Request more claims data| S02
    S05 -->|Declined| DECLINE
    S05 -->|Approved or Overridden| S06
    S06 -->|Terms changed — re-approval needed| S05
    S06 --> GOV
    GOV --> POLICY

    style BROKER fill:#4A90D9,color:#fff,stroke:#2C5F8A
    style POLICY fill:#27AE60,color:#fff,stroke:#1E8449
    style DECLINE fill:#E74C3C,color:#fff,stroke:#C0392B
    style ORCH fill:#8E44AD,color:#fff,stroke:#6C3483
    style GOV fill:#8E44AD,color:#fff,stroke:#6C3483
    style S01 fill:#2980B9,color:#fff,stroke:#1A5276

    style S02 fill:#2980B9,color:#fff,stroke:#1A5276
    style S03 fill:#2980B9,color:#fff,stroke:#1A5276
    style S04 fill:#E67E22,color:#fff,stroke:#CA6F1E
    style S05 fill:#E67E22,color:#fff,stroke:#CA6F1E
    style S06 fill:#2980B9,color:#fff,stroke:#1A5276
```

> **Render this diagram:** VS Code → install the [Markdown Preview Mermaid Support](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid) extension → open Preview (Ctrl+Shift+V). Also renders automatically on GitHub.

---

## Loopback Summary

| From | Back to | Trigger |
|---|---|---|
| `document_ingestion_agent` | Broker (external) | Missing or incomplete documents |
| `underwriting_risk_agent` | `claims_history_agent` | Needs deeper or more specific claims data |
| `underwriting_risk_agent` | `hazard_evaluation_agent` | Needs specific hazard detail not in initial pass |
| `human_in_the_loop` | `document_ingestion_agent` | Underwriter requests additional broker documents |
| `human_in_the_loop` | `claims_history_agent` | Underwriter wants to verify a specific prior claim |
| `pricing_agent` | `human_in_the_loop` | Coverage or terms changed — underwriter must re-approve |

**Key principle:** The orchestrator owns all loopback logic. No agent calls another agent directly.
They return output to the orchestrator, which decides whether to proceed or loop back.
This keeps every loopback logged, intentional, and recoverable.

---

## Cross-Cutting Platform (active throughout)

```
┌──────────────────────────────────────────────────────────────────┐
│  src/underwriting/platform/security          Active at doc ingestion + every  │
│                                 agent boundary. Sanitises input, │
│                                 runs canary token checks.        │
├──────────────────────────────────────────────────────────────────┤
│  src/underwriting/platform/cost_tracking     Active at every LLM call.        │
│                                 Tags policy ID, agent, cost.     │
├──────────────────────────────────────────────────────────────────┤
│  src/underwriting/platform/observability     Active at every state transition.│
│                                 Logs decisions, latency, errors. │
├──────────────────────────────────────────────────────────────────┤
│  src/underwriting/platform/compliance_agent  Active at steps 04, 06, issuance.│
│                                 Checks APRA (AU), RBNZ/FMA (NZ).│
└──────────────────────────────────────────────────────────────────┘
```

---

## Why the Orchestrator Owns Loopbacks

A common mistake in multi-agent systems is letting agents call each other directly. This creates:
- **Circular dependency risk** — Agent A calls B, B calls A, loop never ends
- **Invisible state** — no central record of where the workflow actually is
- **Untraceable audit trail** — impossible to reconstruct the full decision path

In this system, every agent is a **pure function**: receives inputs, returns outputs, done.
The orchestrator is the only entity that knows the full workflow state and decides what
happens next — including whether to loop back. Every loopback is logged, intentional,
and recoverable from any point.
