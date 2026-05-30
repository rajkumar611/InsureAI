from __future__ import annotations

from decimal import Decimal

from pydantic_settings import BaseSettings


class CostSettings(BaseSettings):
    CLAUDE_HAIKU_INPUT_COST_PER_1M: Decimal = Decimal("0.80")
    CLAUDE_HAIKU_OUTPUT_COST_PER_1M: Decimal = Decimal("4.00")
    CLAUDE_SONNET_INPUT_COST_PER_1M: Decimal = Decimal("3.00")
    CLAUDE_SONNET_OUTPUT_COST_PER_1M: Decimal = Decimal("15.00")

    class Config:
        env_file = ".env"
        extra = "ignore"


_settings = CostSettings()

# Maps model ID prefix → (input_cost_per_1M, output_cost_per_1M)
_MODEL_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    "claude-haiku":  (_settings.CLAUDE_HAIKU_INPUT_COST_PER_1M,  _settings.CLAUDE_HAIKU_OUTPUT_COST_PER_1M),
    "claude-sonnet": (_settings.CLAUDE_SONNET_INPUT_COST_PER_1M, _settings.CLAUDE_SONNET_OUTPUT_COST_PER_1M),
}


def calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> Decimal:
    """
    Returns cost in USD for a single LLM call.
    Uses real token counts from the Anthropic API response.
    """
    pricing_key = next(
        (key for key in _MODEL_PRICING if model_id.startswith(key)), None
    )
    if pricing_key is None:
        raise ValueError(f"No pricing configured for model: {model_id!r}")

    input_price, output_price = _MODEL_PRICING[pricing_key]
    million = Decimal("1_000_000")

    return (Decimal(input_tokens) / million * input_price) + \
           (Decimal(output_tokens) / million * output_price)
