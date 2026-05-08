"""Governance schema validation tests."""
from __future__ import annotations

import pytest

from underwriting.platform.governance_agent.schemas import GovernanceDecision, FailedCheck as GovFailedCheck


def test_governance_approved_requires_no_rejection_reasons():
    gd = GovernanceDecision(
        governance_outcome="APPROVED",
        checks_passed=["consistency", "completeness", "compliance", "fraud"],
        checks_failed=[],
        rejection_reasons=[],
        compliance_rules_version="v1.0",
        governance_notes=[],
    )
    assert gd.governance_outcome == "APPROVED"
    assert gd.rejection_reasons == []


def test_governance_rejected_carries_reasons():
    gd = GovernanceDecision(
        governance_outcome="REJECTED",
        checks_passed=["completeness"],
        checks_failed=[
            GovFailedCheck(
                check_name="consistency",
                explanation="Pricing low but hazard EXTREME",
            )
        ],
        rejection_reasons=["Pricing inconsistent with hazard score"],
        compliance_rules_version="v1.0",
        governance_notes=[],
    )
    assert gd.governance_outcome == "REJECTED"
    assert len(gd.checks_failed) == 1
