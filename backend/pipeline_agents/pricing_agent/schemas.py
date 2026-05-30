from __future__ import annotations
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


class PremiumLoading(BaseModel):
    reason: str
    amount: Decimal


class PremiumDiscount(BaseModel):
    reason: str
    amount: Decimal


class PaymentOption(BaseModel):
    frequency: Literal["ANNUAL", "QUARTERLY", "MONTHLY"]
    instalment_amount: Decimal
    total_amount: Decimal


class PricingOutput(BaseModel):
    submission_id: str
    base_premium: Decimal
    risk_loadings: list[PremiumLoading] = Field(default_factory=list)
    claims_loadings: list[PremiumLoading] = Field(default_factory=list)
    discounts: list[PremiumDiscount] = Field(default_factory=list)
    final_premium: Decimal
    premium_currency: str
    excess_recommended: Decimal
    policy_conditions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    payment_options: list[PaymentOption] = Field(default_factory=list)
    premium_rationale: str = ""
    actuarial_table_version: str = ""
    pricing_method: Literal["STANDARD", "SPLIT_JURISDICTION", "MANUAL"] = "STANDARD"
