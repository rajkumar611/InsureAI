"""Governance and compliance schema validation tests."""
from __future__ import annotations

import pytest

from qbe_underwriting.platform.governance_agent.schemas import GovernanceDecision, FailedCheck as GovFailedCheck
from qbe_underwriting.platform.compliance_agent.schemas import ComplianceResult, FailedCheck as CompFailedCheck


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


def test_compliance_blocking_failure_counted():
    cr = ComplianceResult(
        compliance_status="NON_COMPLIANT",
        jurisdiction="NZ",
        compliance_rules_version="v1.0",
        checks_performed=["RBNZ-PROP-001"],
        passed_checks=[],
        failed_checks=[
            CompFailedCheck(
                check_name="RBNZ-PROP-001",
                rule_reference="RBNZ-PROP-001",
                severity="BLOCKING",
                detail="Sum insured exceeds delegated authority limit",
            )
        ],
        blocking_failures=1,
        warnings=[],
        required_actions=["Escalate to senior underwriter"],
        compliance_notes=[],
    )
    assert cr.blocking_failures == 1
    assert cr.compliance_status == "NON_COMPLIANT"


def test_compliance_compliant_zero_blocking():
    cr = ComplianceResult(
        compliance_status="COMPLIANT",
        jurisdiction="AU",
        compliance_rules_version="v1.0",
        checks_performed=["APRA-PROP-001", "APRA-PROP-002"],
        passed_checks=["APRA-PROP-001", "APRA-PROP-002"],
        failed_checks=[],
        blocking_failures=0,
        warnings=[],
        required_actions=[],
        compliance_notes=[],
    )
    assert cr.blocking_failures == 0
    assert cr.compliance_status == "COMPLIANT"
