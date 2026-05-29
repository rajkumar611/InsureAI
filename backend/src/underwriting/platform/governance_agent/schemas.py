from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class FailedCheck(BaseModel):
    check_name: str
    explanation: str


class GovernanceDecision(BaseModel):
    governance_outcome: Literal["APPROVED", "REJECTED", "REFER_TO_SENIOR_UNDERWRITER"]
    checks_passed: list[str] = Field(default_factory=list)
    checks_failed: list[FailedCheck] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    referral_reason: str | None = None
    compliance_rules_version: str
    governance_notes: list[str] = Field(default_factory=list)
