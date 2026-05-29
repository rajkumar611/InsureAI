"""
Unit tests for the LangGraph routing logic in workflow.py.

No LLM calls, no database, no network — pure Python routing logic.
"""
from __future__ import annotations

import pytest

from underwriting.pipeline.underwriting_risk_agent.schemas import RiskAssessment
from underwriting.platform.orchestration.workflow import _needs_human_review, route_after_risk


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_risk(
    decision: str = "ACCEPT",
    risk_score: float = 0.40,
    confidence_score: float = 0.80,
) -> RiskAssessment:
    return RiskAssessment(
        submission_id="test-001",
        risk_decision=decision,
        risk_score=risk_score,
        confidence_score=confidence_score,
    )


def make_state(risk: RiskAssessment) -> dict:
    return {"risk_assessment": risk.model_dump(mode="json")}


# ── _needs_human_review() ─────────────────────────────────────────────────────

def test_refer_always_needs_human_review():
    risk = make_risk(decision="REFER", confidence_score=0.90)
    assert _needs_human_review(risk) is True


def test_accept_low_confidence_needs_human_review():
    risk = make_risk(decision="ACCEPT", confidence_score=0.65)
    assert _needs_human_review(risk) is True


def test_accept_at_threshold_does_not_need_human_review():
    # Confidence exactly 0.70 → auto-approve (boundary inclusive)
    risk = make_risk(decision="ACCEPT", confidence_score=0.70)
    assert _needs_human_review(risk) is False


def test_accept_just_below_threshold_needs_human_review():
    risk = make_risk(decision="ACCEPT", confidence_score=0.699)
    assert _needs_human_review(risk) is True


def test_accept_high_confidence_does_not_need_human_review():
    risk = make_risk(decision="ACCEPT", confidence_score=0.95)
    assert _needs_human_review(risk) is False


def test_decline_does_not_need_human_review():
    risk = make_risk(decision="DECLINE", confidence_score=0.20)
    assert _needs_human_review(risk) is False


# ── route_after_risk() ────────────────────────────────────────────────────────

def test_decline_routes_to_decline_node():
    state = make_state(make_risk(decision="DECLINE", risk_score=0.90, confidence_score=0.85))
    assert route_after_risk(state) == "decline"


def test_refer_routes_to_human_review():
    state = make_state(make_risk(decision="REFER", risk_score=0.65, confidence_score=0.75))
    assert route_after_risk(state) == "human_review"


def test_accept_high_confidence_routes_to_auto_approve():
    state = make_state(make_risk(decision="ACCEPT", risk_score=0.30, confidence_score=0.85))
    assert route_after_risk(state) == "auto_approve"


def test_accept_low_confidence_routes_to_human_review():
    # confidence < 0.70 triggers human review even on ACCEPT
    state = make_state(make_risk(decision="ACCEPT", risk_score=0.35, confidence_score=0.60))
    assert route_after_risk(state) == "human_review"


def test_accept_at_confidence_threshold_routes_to_auto_approve():
    state = make_state(make_risk(decision="ACCEPT", risk_score=0.30, confidence_score=0.70))
    assert route_after_risk(state) == "auto_approve"


def test_accept_just_below_confidence_threshold_routes_to_human_review():
    state = make_state(make_risk(decision="ACCEPT", risk_score=0.30, confidence_score=0.699))
    assert route_after_risk(state) == "human_review"


def test_decline_with_low_confidence_still_routes_to_decline():
    # DECLINE overrides confidence — no human review needed, goes to decline node
    state = make_state(make_risk(decision="DECLINE", risk_score=0.88, confidence_score=0.50))
    assert route_after_risk(state) == "decline"


def test_refer_with_high_confidence_still_routes_to_human_review():
    # REFER always triggers human review regardless of confidence score
    state = make_state(make_risk(decision="REFER", risk_score=0.60, confidence_score=0.95))
    assert route_after_risk(state) == "human_review"
