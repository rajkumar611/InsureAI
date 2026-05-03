from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

HazardLevel = Literal["EXTREME", "HIGH", "MEDIUM", "LOW", "NEGLIGIBLE"]
OverallHazardLevel = Literal["EXTREME", "HIGH", "MEDIUM", "LOW"]


class HazardScore(BaseModel):
    submission_id: str
    flood_risk: HazardLevel = "MEDIUM"
    flood_risk_rationale: str = ""
    fire_risk: HazardLevel = "MEDIUM"
    fire_risk_rationale: str = ""
    structural_risk: HazardLevel = "MEDIUM"
    structural_risk_rationale: str = ""
    environmental_risk: HazardLevel = "MEDIUM"
    environmental_risk_rationale: str = ""
    overall_hazard_level: OverallHazardLevel = "MEDIUM"
    overall_hazard_score: float = Field(ge=0.0, le=1.0, default=0.5)
    key_hazard_factors: list[str] = Field(default_factory=list)
    mitigating_factors: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    data_gaps: list[str] = Field(default_factory=list)
