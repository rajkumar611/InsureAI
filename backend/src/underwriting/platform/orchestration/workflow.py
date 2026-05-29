from __future__ import annotations

import asyncio
import logging
from typing import Literal

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from psycopg_pool import AsyncConnectionPool
from typing_extensions import TypedDict

from underwriting.platform.progress_tracker import set_step
from underwriting.pipeline.claims_history_agent import agent as claims_agent
from underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from underwriting.pipeline.claims_history_agent.schemas import ClaimProfile
from underwriting.pipeline.hazard_evaluation_agent import agent as hazard_agent
from underwriting.pipeline.hazard_evaluation_agent.schemas import HazardScore
from underwriting.pipeline.human_in_the_loop import agent as hitl_agent
from underwriting.pipeline.human_in_the_loop.schemas import UnderwriterDecision
from underwriting.pipeline.pricing_agent import agent as pricing_agent
from underwriting.pipeline.pricing_agent.schemas import PricingOutput
from underwriting.pipeline.underwriting_risk_agent import agent as risk_agent
from underwriting.pipeline.underwriting_risk_agent.schemas import RiskAssessment
from underwriting.platform.audit.writer import record_agent_decision
from underwriting.platform.database.connection import AsyncSessionLocal
from underwriting.platform.governance_agent import agent as governance_agent
from underwriting.platform.governance_agent.schemas import GovernanceDecision

logger = logging.getLogger(__name__)


# ── Workflow state ─────────────────────────────────────────────────────────────
# All values are JSON-serializable so LangGraph can checkpoint them.

class WorkflowState(TypedDict):
    submission_id: str
    class_of_business: str
    jurisdiction: str
    submission_data: dict           # SubmissionData.model_dump(mode="json")
    claim_profile: dict | None      # ClaimProfile.model_dump(mode="json")
    hazard_score: dict | None       # HazardScore.model_dump(mode="json")
    risk_assessment: dict | None    # RiskAssessment.model_dump(mode="json")
    underwriter_decision: dict | None
    pricing_output: dict | None
    governance_decision: dict | None
    workflow_status: str            # RUNNING | AWAITING_HUMAN | COMPLETED | DECLINED | FAILED
    error: str | None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _needs_human_review(risk: RiskAssessment) -> bool:
    if risk.risk_decision == "DECLINE":
        return False
    return risk.risk_decision == "REFER" or risk.confidence_score < 0.70


def _auto_approve(submission_id: str, risk: RiskAssessment) -> UnderwriterDecision:
    """Synthetic approval for ACCEPT cases that bypass human review."""
    return UnderwriterDecision(
        submission_id=submission_id,
        underwriter_id="SYSTEM-AUTO",
        action="APPROVE",
        original_ai_decision=risk.risk_decision,
        original_ai_risk_score=risk.risk_score,
        override_reason=None,
        notes="Auto-approved by system: AI decision was ACCEPT with confidence >= 0.70",
    )


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def parallel_analysis_node(state: WorkflowState) -> dict:
    """Run claims history RAG and hazard evaluation simultaneously."""
    sd = SubmissionData(**state["submission_data"])
    sid = state["submission_id"]
    cob = state["class_of_business"]
    jur = state["jurisdiction"]

    set_step(sid, "parallel_analysis")
    logger.info("workflow: parallel_analysis started  submission=%s", sid)

    async with AsyncSessionLocal() as session:
        claim_profile, hazard_score = await asyncio.gather(
            claims_agent.run(
                submission_id=sid,
                submission_data=sd,
                class_of_business=cob,
                jurisdiction=jur,
                session=session,
            ),
            hazard_agent.run(
                submission_id=sid,
                submission_data=sd,
                class_of_business=cob,
                jurisdiction=jur,
                session=session,
            ),
        )
        await session.commit()

    logger.info(
        "workflow: parallel_analysis done  claims_source=%s  hazard=%s",
        claim_profile.source, hazard_score.overall_hazard_level,
    )
    return {
        "claim_profile": claim_profile.model_dump(mode="json"),
        "hazard_score": hazard_score.model_dump(mode="json"),
    }


async def underwriting_risk_node(state: WorkflowState) -> dict:
    """Synthesise all inputs → Accept / Decline / Refer."""
    sd = SubmissionData(**state["submission_data"])
    cp = ClaimProfile(**state["claim_profile"])
    hs = HazardScore(**state["hazard_score"])
    sid = state["submission_id"]

    set_step(sid, "underwriting_risk")
    logger.info("workflow: underwriting_risk started  submission=%s", sid)

    async with AsyncSessionLocal() as session:
        assessment = await risk_agent.run(
            submission_id=sid,
            submission_data=sd,
            claim_profile=cp,
            hazard_score=hs,
            class_of_business=state["class_of_business"],
            jurisdiction=state["jurisdiction"],
            session=session,
        )
        await session.commit()

    logger.info(
        "workflow: underwriting_risk done  decision=%s  score=%.2f  pre_screen=%s",
        assessment.risk_decision, assessment.risk_score, assessment.pre_screen_triggered,
    )
    return {"risk_assessment": assessment.model_dump(mode="json")}


async def human_review_node(state: WorkflowState) -> dict:
    """
    Enqueue for underwriter review then pause via interrupt().
    Resumes when the caller provides an UnderwriterDecision dict.
    """
    sid = state["submission_id"]
    risk = RiskAssessment(**state["risk_assessment"])

    logger.info("workflow: human_review — enqueuing  submission=%s", sid)

    async with AsyncSessionLocal() as session:
        queue_item = await hitl_agent.enqueue(
            submission_id=sid,
            risk_assessment=risk,
            session=session,
            pipeline_state={
                "submission_data":   state["submission_data"],
                "claim_profile":     state["claim_profile"],
                "hazard_score":      state["hazard_score"],
                "risk_assessment":   state["risk_assessment"],
                "class_of_business": state["class_of_business"],
                "jurisdiction":      state["jurisdiction"],
            },
        )
        await session.commit()
        queue_id = str(queue_item.id)

    logger.info("workflow: human_review — queued  queue_id=%s  waiting for interrupt resume", queue_id)

    # Pause here. The graph caller must resume with an UnderwriterDecision dict.
    decision_data: dict = interrupt({
        "queue_id": queue_id,
        "submission_id": sid,
        "risk_score": risk.risk_score,
        "escalation_reason": risk.escalation_reason,
        "message": "Awaiting underwriter review. Resume with an UnderwriterDecision dict.",
    })

    # Validate what the caller returned
    uw = UnderwriterDecision(**decision_data)
    logger.info("workflow: human_review resumed  action=%s  underwriter=%s", uw.action, uw.underwriter_id)

    async with AsyncSessionLocal() as session:
        await record_agent_decision(
            session=session,
            submission_id=sid,
            agent_name="human_in_the_loop",
            event_type="UNDERWRITER_DECISION",
            decision_value=uw.action,
            decision_rationale=uw.override_reason,
            underwriter_id=uw.underwriter_id,
            override_reason=uw.override_reason,
            parsed_output=uw.model_dump(mode="json"),
        )
        await session.commit()

        queue_item_fresh = await session.get(
            __import__("underwriting.platform.database.models", fromlist=["UnderwriterQueueItem"]).UnderwriterQueueItem,
            __import__("uuid").UUID(queue_id),
        )
        if queue_item_fresh:
            await hitl_agent.record_decision(
                queue_item=queue_item_fresh,
                decision=uw,
                session=session,
            )
        await session.commit()

    return {
        "underwriter_decision": uw.model_dump(mode="json"),
        "workflow_status": "RUNNING",
    }


async def auto_approve_node(state: WorkflowState) -> dict:
    """Create a system auto-approval for ACCEPT cases (confidence >= 0.70)."""
    sid = state["submission_id"]
    risk = RiskAssessment(**state["risk_assessment"])
    uw = _auto_approve(sid, risk)
    logger.info("workflow: auto_approve  submission=%s", sid)
    return {"underwriter_decision": uw.model_dump(mode="json")}


async def pricing_node(state: WorkflowState) -> dict:
    """Calculate premium after confirmed underwriter approval."""
    sid = state["submission_id"]
    sd = SubmissionData(**state["submission_data"])
    risk = RiskAssessment(**state["risk_assessment"])
    uw = UnderwriterDecision(**state["underwriter_decision"])

    set_step(sid, "pricing")
    logger.info("workflow: pricing started  submission=%s", sid)

    async with AsyncSessionLocal() as session:
        output = await pricing_agent.run(
            submission_id=sid,
            submission_data=sd,
            risk_assessment=risk,
            underwriter_decision=uw,
            class_of_business=state["class_of_business"],
            jurisdiction=state["jurisdiction"],
            session=session,
        )
        await session.commit()

    logger.info("workflow: pricing done  final_premium=%s %s", output.final_premium, output.premium_currency)
    return {"pricing_output": output.model_dump(mode="json")}


async def governance_node(state: WorkflowState) -> dict:
    """Final validation of the full workflow chain."""
    sid = state["submission_id"]
    set_step(sid, "governance")
    logger.info("workflow: governance started  submission=%s", sid)

    async with AsyncSessionLocal() as session:
        decision = await governance_agent.run(
            submission_id=sid,
            submission_data=SubmissionData(**state["submission_data"]),
            claim_profile=ClaimProfile(**state["claim_profile"]),
            hazard_score=HazardScore(**state["hazard_score"]),
            risk_assessment=RiskAssessment(**state["risk_assessment"]),
            underwriter_decision=UnderwriterDecision(**state["underwriter_decision"]),
            pricing_output=PricingOutput(**state["pricing_output"]),
            class_of_business=state["class_of_business"],
            jurisdiction=state["jurisdiction"],
            session=session,
        )
        await session.commit()

    status = (
        "COMPLETED"
        if decision.governance_outcome == "APPROVED"
        else "AWAITING_SENIOR_REVIEW"
        if decision.governance_outcome == "REFER_TO_SENIOR_UNDERWRITER"
        else "GOVERNANCE_REJECTED"
    )

    logger.info("workflow: governance done  outcome=%s", decision.governance_outcome)
    return {
        "governance_decision": decision.model_dump(mode="json"),
        "workflow_status": status,
    }


async def decline_node(state: WorkflowState) -> dict:
    """Terminal node for pre-screen DECLINE decisions — no pricing or governance needed."""
    sid = state["submission_id"]
    rule = state["risk_assessment"]["pre_screen_rule"]
    logger.info("workflow: declined  submission=%s  rule=%s", sid, rule)
    return {"workflow_status": "DECLINED"}


# ── Routing functions ──────────────────────────────────────────────────────────

def route_after_risk(state: WorkflowState) -> Literal["decline", "auto_approve", "human_review"]:
    risk = RiskAssessment(**state["risk_assessment"])
    if risk.risk_decision == "DECLINE":
        return "decline"
    if _needs_human_review(risk):
        return "human_review"
    return "auto_approve"


# ── Graph construction ─────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    g = StateGraph(WorkflowState)

    g.add_node("parallel_analysis", parallel_analysis_node)
    g.add_node("underwriting_risk", underwriting_risk_node)
    g.add_node("human_review", human_review_node)
    g.add_node("auto_approve", auto_approve_node)
    g.add_node("pricing", pricing_node)
    g.add_node("governance", governance_node)
    g.add_node("decline", decline_node)

    g.add_edge(START, "parallel_analysis")
    g.add_edge("parallel_analysis", "underwriting_risk")
    g.add_conditional_edges(
        "underwriting_risk",
        route_after_risk,
        {"decline": "decline", "auto_approve": "auto_approve", "human_review": "human_review"},
    )
    g.add_edge("auto_approve", "pricing")
    g.add_edge("human_review", "pricing")
    g.add_edge("pricing", "governance")
    g.add_edge("governance", END)
    g.add_edge("decline", END)

    return g


_pool: AsyncConnectionPool | None = None
graph = None


async def init_workflow(db_url: str) -> None:
    """Call once at app startup to wire up the Postgres checkpointer."""
    global _pool, graph
    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    _pool = AsyncConnectionPool(
        conninfo=pg_url,
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    await _pool.open()
    checkpointer = AsyncPostgresSaver(_pool)
    await checkpointer.setup()
    graph = _build_graph().compile(checkpointer=checkpointer)
    logger.info("workflow: Postgres checkpointer ready")


async def close_workflow() -> None:
    """Call at app shutdown to close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("workflow: connection pool closed")


# ── Public API ─────────────────────────────────────────────────────────────────

async def run_pipeline(
    *,
    submission_id: str,
    submission_data: SubmissionData,
    class_of_business: str,
    jurisdiction: str,
    thread_id: str | None = None,
) -> WorkflowState:
    """
    Run the full underwriting pipeline for a submission.

    Returns the final WorkflowState. If the state machine pauses at
    human_review, workflow_status will be "AWAITING_HUMAN" and the
    caller should resume with resume_pipeline() after obtaining an
    UnderwriterDecision.
    """
    tid = thread_id or submission_id
    config = {"configurable": {"thread_id": tid}}

    initial: WorkflowState = {
        "submission_id": submission_id,
        "class_of_business": class_of_business,
        "jurisdiction": jurisdiction,
        "submission_data": submission_data.model_dump(mode="json"),
        "claim_profile": None,
        "hazard_score": None,
        "risk_assessment": None,
        "underwriter_decision": None,
        "pricing_output": None,
        "governance_decision": None,
        "workflow_status": "RUNNING",
        "error": None,
    }

    logger.info("workflow: run_pipeline started  submission=%s  thread=%s", submission_id, tid)

    try:
        final = await graph.ainvoke(initial, config=config)
    except Exception as exc:
        logger.error("workflow: pipeline failed  submission=%s  error=%s", submission_id, exc, exc_info=True)
        raise

    # LangGraph returns the checkpointed state when interrupt() fires.
    # At that point no node has updated workflow_status, so it stays "RUNNING".
    # Detect the paused state and set the correct status so callers and the DB
    # can distinguish "still processing" from "waiting for underwriter".
    if (
        final.get("workflow_status") == "RUNNING"
        and final.get("risk_assessment") is not None
        and final.get("underwriter_decision") is None
    ):
        final["workflow_status"] = "AWAITING_HUMAN"

    logger.info(
        "workflow: run_pipeline finished  submission=%s  status=%s",
        submission_id, final.get("workflow_status"),
    )
    return final


async def resume_pipeline(
    *,
    thread_id: str,
    underwriter_decision: UnderwriterDecision,
) -> WorkflowState:
    """
    Resume a pipeline that paused at human_review.

    Call this after an underwriter submits their decision via the UI/API.
    thread_id is the same submission_id used in run_pipeline().
    """
    config = {"configurable": {"thread_id": thread_id}}
    decision_data = underwriter_decision.model_dump(mode="json")

    logger.info("workflow: resume_pipeline  thread=%s  action=%s", thread_id, underwriter_decision.action)

    final = await graph.ainvoke(
        # Command tells LangGraph to resume and provide the interrupt value
        __import__("langgraph.types", fromlist=["Command"]).Command(resume=decision_data),
        config=config,
    )
    logger.info(
        "workflow: resume_pipeline done  thread=%s  status=%s",
        thread_id, final.get("workflow_status"),
    )
    return final
