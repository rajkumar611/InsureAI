# Project Approach & Phases — InsureAI

How the project evolved, what problems were solved, and why decisions were made.

---

## Phase 1: Core Agent System (MVP)

**Timeline:** 2025-04-15 to 2025-05-01  
**Goal:** Build 6 LLM agents with workflow orchestration  
**Decision Drivers:** Portfolio quality, AI engineering focus, cost transparency

### What We Built

6 agents in a LangGraph StateGraph pipeline:
1. **Document Ingestion** (Haiku) — Extract structured data from unstructured text
2. **Claims History** (Haiku + pgvector) — RAG search for customer's claim history
3. **Hazard Evaluation** (Sonnet) — Assess geographic/hazard risk
4. **Underwriting Risk** (Sonnet) — Pre-screen deterministic rules + LLM synthesis
5. **Human-in-the-Loop** — Escalate borderline cases for underwriter review
6. **Pricing** (Haiku) — Apply loadings/discounts to base rates
7. **Governance** (Sonnet) — Final compliance checkpoint

**Why this order?**
- Deterministic pre-screening first (fast, cheap)
- Parallel hazard + claims analysis (no ordering dependencies)
- LLM synthesis for risk only (most expensive decision)
- Human escalation **before** pricing (don't price what we haven't approved)
- Governance last (final checkpoint)

### Key Design Decisions

#### 1. **LangGraph StateGraph over Custom Orchestration**

**Decision:** Use LangGraph instead of hand-rolled state machine.

**Why?**
- State management is hard: each agent needs input validation, output parsing, error handling
- LangGraph gives: explicit node dependencies, conditional routing, built-in state checkpointing
- Conditional edges handle REFER/ACCEPT/DECLINE branching cleanly
- PostgreSQL checkpointer enables HITL (pause workflow, wait for human, resume)

**Code Example:**
```python
graph = StateGraph(WorkflowState)
graph.add_node("ingestion", ingest_node)
graph.add_node("risk", risk_node)
graph.add_conditional_edges(
    "risk",
    lambda state: "pricing" if state.decision == "ACCEPT" else "governance"
)
```

**Lesson:** Explicit routing > implicit control flow. Future engineers can read the graph and understand execution order immediately.

---

#### 2. **RAG with 3-Tier Fallback vs Single Vector Search**

**Decision:** Exact match → Fuzzy name → Semantic search (pgvector).

**Why?**
- Exact match (ABN/NZBN): 100% precision, catches most customers immediately
- Fuzzy name match: 80% confidence, handles typos/variations
- Semantic search: 60% confidence, fallback for edge cases

**Problem We Avoided:**
If we used only pgvector:
- "Motor" vehicle claim and "Property" garage claim both match "vehicle damage" semantically
- False positives waste tokens and confuse risk assessment
- No business logic filtering = garbage in, garbage out

**Lesson:** RAG precision > recall. Better to miss a claim than misattribute one. Business logic should filter semantic results.

---

#### 3. **Deterministic Pre-Screen Before LLM**

**Decision:** Fast rules first (hazard+claims rules), reserve Sonnet for edge cases.

**Why?**
- 95% of submissions are obviously ACCEPT or DECLINE
- Running all through Sonnet (best reasoning) = 3x cost, no benefit
- Rules are deterministic: "claims > 5 → DECLINE", "high hazard + high claims → REFER"

**Math:**
- Sonnet costs 3x more than Haiku per token
- Pre-screening saves ~90 LLM calls per 100 submissions
- At 1000 submissions/month = ~$500/month savings

**Lesson:** Expensive resources (Sonnet) go to hard problems (edge cases). Easy problems solved cheaply first.

---

#### 4. **Cost Transparency Built In**

**Decision:** Track every token, calculate USD cost immediately, log everything.

**Why?**
- LLMs are expensive; need to know where money goes
- "Cost per submission" is a business metric (finance cares)
- Insurance is regulated; audit trail is required
- Cost tracking enables optimization: "claims_agent costs 3x more than others, why?"

**Implementation:** Middleware that captures response.usage after every LLM call:
```python
cost_usd = calculate_cost(
    model=model,
    input_tokens=response.usage.input_tokens,
    output_tokens=response.usage.output_tokens
)
```

**Lesson:** Logging costs is not optional. Real token counts from API response, not estimates.

---

## Phase 2: Public API & Validation (Scalable)

**Timeline:** 2025-05-01 to 2025-05-15  
**Goal:** Make the system production-ready with proper inputs + rate limiting  
**Decision Drivers:** Security, scalability, compliance

### What We Built

**FastAPI public REST API** with 10 endpoints:
- `/health`, `/health/ready` — Liveness & readiness
- `/api/v1/submissions/*` — CRUD operations
- `/api/v1/submissions/pipeline` — Trigger workflow
- `/api/v1/queue/*` — HITL escalation
- `/api/v1/audit/*` — Cost tracking

**No Authentication.** Direct submission by underwriters (SaaS model).

### Key Design Decisions

#### 1. **Public API (No Broker Authentication)**

**Decision:** Remove broker authentication, allow direct underwriter submission.

**Why?**
- Original design had broker users (system intermediaries)
- Insurance underwriters ARE the users → direct submission better
- No authentication overhead = faster API, simpler integration
- Trust is at infrastructure layer (IP whitelist, API gateway), not code

**Impact:**
- Removed: broker_id from submission, broker auth middleware
- Added: submission_ref (external reference for tracking)
- Result: Cleaner code, simpler mental model

**Lesson:** Authentication should match your user model. Brokers-as-middlemen added complexity; underwriters-as-direct-users simplified it.

---

#### 2. **Rate Limiting (In-Memory, Not Redis)**

**Decision:** Use in-memory rate limiter for MVP (no Redis dependency).

**Why?**
- Single API instance → in-memory is fine
- Redis adds deployment complexity (extra service, networking, failover)
- Can migrate to Redis later if scaling to multiple instances

**Limit:** 10 submissions/day per IP (business decision, not technical)

**Lesson:** Defer complexity. Start simple (in-memory), graduate to Redis if needed.

---

#### 3. **Input Validation (Pydantic)**

**Decision:** Strict schema validation at API boundary.

**Why?**
- Garbage in → garbage out
- Pydantic catches invalid input before it reaches agents
- Example: Missing "class_of_business" field → 400 Bad Request, not silent failure

**Lesson:** Validate at system boundaries (user input). Trust internal code.

---

## Phase 3: Production Deployment (AWS EKS)

**Timeline:** 2025-05-15 to 2025-05-31  
**Goal:** Deploy to Kubernetes with proper scaling, persistence, and observability  
**Decision Drivers:** Reliability, observability, cloud-native best practices

### What We Built

**AWS EKS cluster** with:
- API deployment (2 replicas) + LoadBalancer service
- Dashboard deployment (1 replica) + LoadBalancer service
- PostgreSQL StatefulSet with persistent volume
- GitHub Actions CI/CD pipeline (build → push → deploy)

### Key Design Decisions & Problems Solved

#### 1. **PostgreSQL Checkpointing for HITL**

**Problem:** Workflow runs, gets paused for human review, then needs to resume with exact context.

**Challenge:**
- In-memory state = lost if pod crashes
- Multiple API instances = state conflicts
- "Underwriter said REFER, but API doesn't remember" = data loss

**Solution:** LangGraph PostgreSQL checkpointer.
```python
checkpointer = AsyncPostgresSaver(db_connection)
graph = compiled_graph.compile(checkpointer=checkpointer)

# State persisted after each agent
await graph.ainvoke(input_data, config={"configurable": {"thread_id": submission_id}})

# Resume from checkpoint if interrupted
await graph.aupdate_state(
    {"decision": underwriter_decision},
    config={"configurable": {"thread_id": submission_id}}
)
```

**Lesson:** Stateful workflows need durable checkpointing. Database is your source of truth.

---

#### 2. **Multi-Layer Authentication (IAM → RBAC → Secrets)**

**Problem:** kubectl commands failing with "unauthorized" even with AWS credentials.

**Root Cause:** Three independent layers must align:
1. **AWS IAM** — Who are you? (rajaiazkb user)
2. **EKS Access Entry** — Can you access the cluster? (user not in list)
3. **Kubernetes RBAC** — What can you do? (no ClusterRoleBinding)

**Solution:**
- Add user to EKS Access tab (AWS Console)
- Assign AmazonEKSAdminPolicy + "admins" group
- ImagePullSecrets in deployment (ECR credentials)

**Lesson:** Authentication is layered. Each layer is necessary; missing one = failure.

---

#### 3. **Subnet Tagging for LoadBalancer**

**Problem:** External IP stuck in <pending> for 18+ hours.

**Root Cause:** AWS ELB needs to find the right subnets automatically.

**Solution:** Tag all 3 subnets:
```
kubernetes.io/role/internal-elb=1
```

**Lesson:** Infrastructure has invisible requirements. Read the error logs. Debug systemically.

---

#### 4. **GitHub Actions Workflow Ordering**

**Problem:** Pipeline failing at different stages (ECR secret created before namespace, statefulset immutable field errors, etc.).

**Root Cause:** Each step has dependencies; order matters.

**Solution:** Strict ordering:
1. Get kubeconfig (authenticate)
2. Login to ECR (credentials)
3. Apply manifests (creates namespace, resources)
4. Create ECR secret (in that namespace)
5. Update deployments
6. Wait for rollout

**Lesson:** Infrastructure-as-code is still imperative. Dependencies must be explicit.

---

## Key Lessons Across All Phases

### 1. **Explicit > Implicit**

- Explicit node dependencies (LangGraph) > implicit control flow
- Explicit routing logic (conditional edges) > magic branching
- Explicit state checksums (logged prompts) > "trust it worked"

### 2. **Business Logic First, Then Infrastructure**

- Multi-agent orchestration is **AI problem**, not ops problem
- RAG precision/recall tradeoff is **business problem**, not data problem
- Cost optimization is **economics problem**, not just engineering

### 3. **Validation at Boundaries**

- Validate user input (API schema)
- Trust internal code (no defensive copying)
- Log everything (audit trail)

### 4. **Defer Complexity**

- Start with in-memory rate limiter (works)
- Graduate to Redis (scales)
- Don't architect for Scale™ on day 1

### 5. **Production Readiness is Unglamorous**

- Most work is boring infrastructure (networking, auth, logging)
- Few lines of AI code, many lines of plumbing
- That's normal and fine

---

## What's Missing (Not Attempted)

### Azure AD Integration
**Status:** Not implemented.  
**Why:** CLAUDE.md says "NO User/Underwriter table yet"  
**What's needed:** User model + bearer token validation + RBAC for departments

### Redis Rate Limiting
**Status:** In-memory only.  
**Why:** Single instance is sufficient.  
**When to add:** If deploying multiple API replicas

### React Frontend
**Status:** Streamlit only.  
**Why:** MVP doesn't require React UX sophistication.  
**When to add:** If underwriters demand custom UI

### Webhook Notifications
**Status:** Not implemented.  
**Why:** Polling is sufficient for MVP.  
**When to add:** If integrating with external systems

### Prompt Injection Detector
**Status:** Handled in prompts only.  
**Why:** Python-level sanitization not critical for MVP.  
**When to add:** If attack surface expands

---

## Evolution Timeline

```
Phase 1 (MVP)
├─ 6 agents + LangGraph
├─ PostgreSQL + pgvector
├─ Cost tracking
└─ Streamlit UI

Phase 2 (Public API)
├─ FastAPI 10 endpoints
├─ Rate limiting
├─ Input validation
└─ Removed broker auth

Phase 3 (Production)
├─ AWS EKS deployment
├─ GitHub Actions CI/CD
├─ PostgreSQL checkpointing
└─ Multi-layer auth

Phase 4 (Future)
├─ Azure AD integration
├─ Streaming results
├─ Redis rate limiter
└─ React frontend
```

---

**Document Status:** Complete  
**Last Updated:** 2026-06-01  
**Next Review:** When Phase 4 starts
