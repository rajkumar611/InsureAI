from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class FailedCheck(BaseModel):
    check_name: str
    rule_reference: str
    severity: Literal["BLOCKING", "WARNING"]
    detail: str


class ComplianceResult(BaseModel):
    compliance_status: Literal[
        "COMPLIANT", "NON_COMPLIANT", "PENDING_REVIEW", "REFER_TO_COMPLIANCE_TEAM"
    ]
    jurisdiction: str
    compliance_rules_version: str
    checks_performed: list[str] = Field(default_factory=list)
    passed_checks: list[str] = Field(default_factory=list)
    failed_checks: list[FailedCheck] = Field(default_factory=list)
    blocking_failures: int = 0
    warnings: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    compliance_notes: list[str] = Field(default_factory=list)
