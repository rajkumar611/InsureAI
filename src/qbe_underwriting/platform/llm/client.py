from __future__ import annotations

import anthropic
from pydantic_settings import BaseSettings


class LLMSettings(BaseSettings):
    ANTHROPIC_API_KEY: str
    ANTHROPIC_REQUESTS_PER_MINUTE: int = 50
    ANTHROPIC_TOKENS_PER_MINUTE: int = 200000

    class Config:
        env_file = ".env"
        extra = "ignore"


_settings = LLMSettings()

# Shared async Anthropic client — one instance for the whole app
anthropic_client = anthropic.AsyncAnthropic(api_key=_settings.ANTHROPIC_API_KEY)

# Model routing — each agent uses the right model for its complexity
MODEL_FOR_AGENT: dict[str, str] = {
    "document_ingestion_agent": "claude-haiku-4-5-20251001",
    "claims_history_agent":     "claude-haiku-4-5-20251001",
    "hazard_evaluation_agent":  "claude-sonnet-4-6",
    "underwriting_risk_agent":  "claude-sonnet-4-6",
    "governance_agent":         "claude-sonnet-4-6",
    "compliance_agent":         "claude-sonnet-4-6",
    "pricing_agent":            "claude-haiku-4-5-20251001",
}


def model_for(agent_name: str) -> str:
    if agent_name not in MODEL_FOR_AGENT:
        raise ValueError(f"No model configured for agent: {agent_name!r}")
    return MODEL_FOR_AGENT[agent_name]
