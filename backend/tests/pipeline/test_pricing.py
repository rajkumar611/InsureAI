"""
Unit tests for the deterministic _compute_premium() function in pricing_agent.

No LLM calls, no database, no network — pure Python logic.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from underwriting.pipeline.pricing_agent.agent import _compute_premium, _market_rates

NZ_RATES = _market_rates("property", "NZ")
AU_RATES = _market_rates("property", "AU")


# ── Helpers ───────────────────────────────────────────────────────────────────

def compute(
    sum_insured: float = 5_000_000,
    risk_score: float = 0.30,
    security_features: list[str] | None = None,
    year_built: int | None = None,
    excess_requested: float | None = None,
    mitigating_factors: list[str] | None = None,
    rates: dict | None = None,
) -> dict:
    return _compute_premium(
        sum_insured=Decimal(str(sum_insured)),
        rates=rates or NZ_RATES,
        risk_score=risk_score,
        security_features=security_features or [],
        year_built=year_built,
        excess_requested=Decimal(str(excess_requested)) if excess_requested else None,
        mitigating_factors=mitigating_factors or [],
    )


# ── Base premium calculation ──────────────────────────────────────────────────

def test_base_premium_uses_rate_per_mille():
    # NZ property base rate = 1.20 per mille → 5M * 1.20 / 1000 = NZD 6,000
    result = compute(sum_insured=5_000_000)
    assert result["base_premium"] == Decimal("6000.00")


def test_base_premium_scales_with_sum_insured():
    result_10m = compute(sum_insured=10_000_000)
    result_5m = compute(sum_insured=5_000_000)
    assert result_10m["base_premium"] == result_5m["base_premium"] * 2


# ── Risk score loadings ───────────────────────────────────────────────────────

def test_no_loading_for_low_risk_score():
    result = compute(risk_score=0.30)
    assert result["risk_loadings"] == []


def test_elevated_loading_for_score_between_40_and_60():
    # 0.40 ≤ score < 0.60 → +10% of base
    result = compute(sum_insured=5_000_000, risk_score=0.45)
    base = Decimal("6000.00")
    expected_loading = (base * Decimal("0.10")).quantize(Decimal("0.01"))
    assert len(result["risk_loadings"]) == 1
    assert result["risk_loadings"][0]["amount"] == expected_loading


def test_high_loading_for_score_above_60():
    # score ≥ 0.60 → +20% of base
    result = compute(sum_insured=5_000_000, risk_score=0.65)
    base = Decimal("6000.00")
    expected_loading = (base * Decimal("0.20")).quantize(Decimal("0.01"))
    assert len(result["risk_loadings"]) == 1
    assert result["risk_loadings"][0]["amount"] == expected_loading


def test_loading_boundary_at_0_60():
    result_just_below = compute(risk_score=0.599)
    result_at_boundary = compute(risk_score=0.60)
    # 0.599 → elevated (10%), 0.60 → high (20%)
    assert result_just_below["risk_loadings"][0]["amount"] < result_at_boundary["risk_loadings"][0]["amount"]


# ── Discounts ─────────────────────────────────────────────────────────────────

def test_sprinkler_discount_applied():
    result = compute(security_features=["Automatic sprinkler system"])
    reasons = [d["reason"] for d in result["discounts"]]
    assert any("sprinkler" in r.lower() for r in reasons)


def test_monitored_alarm_discount_applied():
    result = compute(security_features=["Monitored alarm 24/7"])
    reasons = [d["reason"] for d in result["discounts"]]
    assert any("alarm" in r.lower() or "monitor" in r.lower() for r in reasons)


def test_post_2000_build_discount_applied():
    result = compute(year_built=2015)
    reasons = [d["reason"] for d in result["discounts"]]
    assert any("2015" in r or "post-2000" in r.lower() or "post_2000" in r.lower() or "construction" in r.lower() for r in reasons)


def test_pre_2000_build_no_discount():
    result = compute(year_built=1985)
    reasons = [d["reason"] for d in result["discounts"]]
    assert not any("1985" in r for r in reasons)


def test_no_claims_discount_from_mitigating_factors():
    result = compute(mitigating_factors=["No claims in 3 years"])
    reasons = [d["reason"] for d in result["discounts"]]
    assert any("claim" in r.lower() for r in reasons)


def test_multiple_discounts_accumulate():
    result = compute(
        security_features=["Automatic sprinkler system", "Monitored alarm"],
        year_built=2010,
    )
    assert len(result["discounts"]) >= 2


# ── Technical minimum ─────────────────────────────────────────────────────────

def test_technical_minimum_enforced_for_tiny_sum_insured():
    # 100k * 1.20/1000 = NZD 120 — below NZD 750 technical min
    result = compute(sum_insured=100_000, risk_score=0.10)
    assert result["final_premium"] >= Decimal("750")


def test_technical_minimum_not_applied_when_premium_is_above():
    result = compute(sum_insured=5_000_000)
    assert result["final_premium"] > Decimal("750")


# ── Excess rules ──────────────────────────────────────────────────────────────

def test_excess_is_ten_percent_of_final_premium():
    result = compute(sum_insured=5_000_000, risk_score=0.30)
    final = result["final_premium"]
    excess = result["excess_recommended"]
    # Must be within one rounding increment (100) of 10% of final
    expected_raw = final * Decimal("0.10")
    assert abs(excess - expected_raw) < Decimal("100")


def test_excess_is_multiple_of_100():
    result = compute(sum_insured=5_000_000, risk_score=0.50)
    excess = result["excess_recommended"]
    assert excess % 100 == 0, f"Excess {excess} is not a multiple of 100"


def test_excess_is_multiple_of_100_with_high_risk():
    result = compute(sum_insured=12_000_000, risk_score=0.75)
    excess = result["excess_recommended"]
    assert excess % 100 == 0, f"Excess {excess} is not a multiple of 100"


def test_excess_minimum_is_100():
    # Technical minimum kicks in but excess must still be at least 100
    result = compute(sum_insured=50_000, risk_score=0.10)
    assert result["excess_recommended"] >= Decimal("100")


def test_excess_never_exceeds_final_premium():
    for sum_insured in [100_000, 500_000, 5_000_000, 20_000_000]:
        result = compute(sum_insured=sum_insured, risk_score=0.50)
        assert result["excess_recommended"] <= result["final_premium"], (
            f"sum_insured={sum_insured}: excess {result['excess_recommended']} "
            f"> final_premium {result['final_premium']}"
        )


def test_excess_never_equals_final_premium_except_at_minimum():
    # For a normal-sized risk, excess should be strictly less than final premium
    result = compute(sum_insured=5_000_000, risk_score=0.30)
    assert result["excess_recommended"] < result["final_premium"]


# ── Payment options ───────────────────────────────────────────────────────────

def test_payment_options_include_all_frequencies():
    result = compute()
    frequencies = {p["frequency"] for p in result["payment_options"]}
    assert frequencies == {"ANNUAL", "QUARTERLY", "MONTHLY"}


def test_annual_payment_equals_final_premium():
    result = compute(sum_insured=5_000_000, risk_score=0.30)
    final = result["final_premium"]
    annual = next(p for p in result["payment_options"] if p["frequency"] == "ANNUAL")
    assert annual["instalment_amount"] == final


def test_monthly_payment_is_final_divided_by_12():
    result = compute(sum_insured=5_000_000, risk_score=0.30)
    final = result["final_premium"]
    monthly = next(p for p in result["payment_options"] if p["frequency"] == "MONTHLY")
    expected = (final / 12).quantize(Decimal("0.01"))
    assert monthly["instalment_amount"] == expected


def test_quarterly_payment_is_final_divided_by_4():
    result = compute(sum_insured=5_000_000, risk_score=0.30)
    final = result["final_premium"]
    quarterly = next(p for p in result["payment_options"] if p["frequency"] == "QUARTERLY")
    expected = (final / 4).quantize(Decimal("0.01"))
    assert quarterly["instalment_amount"] == expected


# ── Currency / jurisdiction ───────────────────────────────────────────────────

def test_nz_currency_is_nzd():
    result = compute(rates=NZ_RATES)
    assert result["premium_currency"] == "NZD"


def test_au_currency_is_aud():
    result = compute(rates=AU_RATES)
    assert result["premium_currency"] == "AUD"


def test_au_base_rate_higher_than_nz():
    # AU fire loading is higher — base rate should produce higher premium for same SI
    nz = compute(sum_insured=5_000_000, rates=NZ_RATES)
    au = compute(sum_insured=5_000_000, rates=AU_RATES)
    assert au["base_premium"] > nz["base_premium"]
