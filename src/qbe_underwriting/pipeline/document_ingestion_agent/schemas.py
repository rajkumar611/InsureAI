from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

# LLMs sometimes return null for list fields — coerce to empty list
NullableList = Annotated[list[str], BeforeValidator(lambda v: v or [])]


class SubmissionData(BaseModel):
    submission_id: str
    insured_name: str | None = None
    insured_abn_or_registration: str | None = None
    insured_address: str | None = None
    insured_contact_name: str | None = None
    insured_contact_email: str | None = None
    insured_contact_phone: str | None = None
    risk_address: str | None = None
    construction_type: str | None = None
    year_built: int | None = None
    number_of_storeys: int | None = None
    gross_floor_area_sqm: float | None = None
    occupancy_type: str | None = None
    security_features: NullableList = Field(default_factory=list)
    sum_insured: Decimal | None = None
    sum_insured_currency: str | None = None
    coverage_type: str | None = None
    policy_period_start: str | None = None
    policy_period_end: str | None = None
    excess_requested: Decimal | None = None
    declared_claims_last_5_years: int | None = None
    declared_largest_loss: Decimal | None = None
    declared_largest_loss_currency: str | None = None
    declared_claims_description: str | None = None
    document_types_identified: NullableList = Field(default_factory=list)
    confirmed_class_of_business: Literal[
        "property", "liability", "marine", "motor", "specialty", "mixed", "unknown"
    ] = "unknown"
    extraction_confidence: Literal["high", "medium", "low"] = "low"
    anomalies: NullableList = Field(default_factory=list)
    missing_required_fields: NullableList = Field(default_factory=list)
