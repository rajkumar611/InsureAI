"""Schema validation tests — no DB, no LLM, pure Pydantic."""
from __future__ import annotations

from decimal import Decimal

import pytest

from underwriting.pipeline.document_ingestion_agent.schemas import SubmissionData
from underwriting.pipeline.claims_history_agent.schemas import ClaimProfile
from underwriting.pipeline.hazard_evaluation_agent.schemas import HazardScore
from underwriting.pipeline.underwriting_risk_agent.schemas import RiskAssessment
from underwriting.pipeline.pricing_agent.schemas import PricingOutput, PremiumLoading


def test_submission_data_defaults_to_unknown_class():
    s = SubmissionData(submission_id="SUB-001")
    assert s.confirmed_class_of_business == "unknown"
    assert s.extraction_confidence == "low"
    assert s.anomalies == []


def test_submission_data_rejects_invalid_class():
    with pytest.raises(Exception):
        SubmissionData(submission_id="SUB-001", confirmed_class_of_business="invalid")


def test_claim_profile_defaults():
    cp = ClaimProfile(submission_id="SUB-001", source="BENCHMARK")
    assert cp.total_claims_3yr == 0
    assert cp.data_quality == "LOW"
    assert cp.risk_flags == []


def test_hazard_score_confidence_bounds():
    with pytest.raises(Exception):
        HazardScore(submission_id="SUB-001", confidence=1.5)


def test_risk_assessment_score_bounds():
    with pytest.raises(Exception):
        RiskAssessment(
            submission_id="SUB-001",
            risk_decision="ACCEPT",
            risk_score=1.5,
            confidence_score=0.8,
        )


def test_risk_assessment_valid_decisions():
    for decision in ("ACCEPT", "DECLINE", "REFER"):
        ra = RiskAssessment(
            submission_id="SUB-001",
            risk_decision=decision,
            risk_score=0.5,
            confidence_score=0.8,
        )
        assert ra.risk_decision == decision


def test_pricing_output_loadings_accumulate():
    po = PricingOutput(
        submission_id="SUB-001",
        base_premium=Decimal("5000"),
        final_premium=Decimal("6500"),
        premium_currency="NZD",
        excess_recommended=Decimal("10000"),
        risk_loadings=[
            PremiumLoading(reason="Flood zone HIGH", amount=Decimal("1000")),
            PremiumLoading(reason="Claim history", amount=Decimal("500")),
        ],
    )
    total_loadings = sum(l.amount for l in po.risk_loadings)
    assert total_loadings == Decimal("1500")
