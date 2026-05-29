from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class UnderwriterDecision(BaseModel):
    submission_id: str
    underwriter_id: str
    action: Literal[
        "APPROVE",
        "APPROVE_WITH_CONDITIONS",
        "OVERRIDE",
        "DECLINE",
        "REQUEST_MORE_DOCUMENTS",
        "REQUEST_MORE_CLAIMS_DATA",
        "ESCALATE_TO_SENIOR",
    ]
    original_ai_decision: Literal["ACCEPT", "DECLINE", "REFER"]
    original_ai_risk_score: float = Field(ge=0.0, le=1.0)
    override_risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    override_reason: str | None = None
    conditions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    supporting_documents: list[str] = Field(default_factory=list)
    notes: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def effective_risk_score(self) -> float:
        return self.override_risk_score if self.override_risk_score is not None else self.original_ai_risk_score
