from __future__ import annotations
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


ClaimRiskFlag = Literal[
    "REPEAT_FLOOD", "REPEAT_FIRE", "LARGE_LOSS_LAST_12M", "HIGH_FREQUENCY",
    "FRAUD_SUSPICION", "CATASTROPHE_EXPOSURE", "NO_HISTORY", "BENCHMARK_ONLY",
]


class ClaimProfile(BaseModel):
    submission_id: str
    source: Literal["CUSTOMER_HISTORY", "BENCHMARK", "PARTIAL"]
    total_claims_3yr: int = 0
    total_claims_5yr: int = 0
    total_incurred_3yr: Decimal = Decimal("0")
    total_incurred_5yr: Decimal = Decimal("0")
    largest_single_loss: Decimal = Decimal("0")
    largest_loss_cause: str | None = None
    most_common_cause: str | None = None
    claim_frequency_trend: Literal["INCREASING", "STABLE", "DECREASING", "INSUFFICIENT_DATA"] = (
        "INSUFFICIENT_DATA"
    )
    risk_flags: list[ClaimRiskFlag] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    data_quality: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
