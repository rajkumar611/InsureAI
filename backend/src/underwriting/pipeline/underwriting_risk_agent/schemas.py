from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class RiskAssessment(BaseModel):
    submission_id: str
    risk_decision: Literal["ACCEPT", "DECLINE", "REFER"]
    risk_score: float = Field(ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    pre_screen_triggered: bool = False
    pre_screen_rule: str | None = None
    primary_risk_factors: list[str] = Field(default_factory=list)
    mitigating_factors: list[str] = Field(default_factory=list)
    signal_conflict: bool = False
    signal_conflict_explanation: str | None = None
    applicable_guidelines: list[str] = Field(default_factory=list)
    decision_rationale: str = ""
    escalation_reason: str | None = None
