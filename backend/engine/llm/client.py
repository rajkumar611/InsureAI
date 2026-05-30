from __future__ import annotations

import os

import anthropic
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class LLMSettings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    ANTHROPIC_API_KEY: str
    ANTHROPIC_REQUESTS_PER_MINUTE: int = 50
    ANTHROPIC_TOKENS_PER_MINUTE: int = 200000


_settings = LLMSettings()

# Shared async Anthropic client — one instance for the whole app
anthropic_client = anthropic.AsyncAnthropic(api_key=_settings.ANTHROPIC_API_KEY)

# Model routing — each agent uses the right model for its complexity
MODEL_FOR_AGENT: dict[str, str] = {
    "document_ingestion_agent": os.getenv("MODEL_INGESTION",  "claude-haiku-4-5-20251001"),
    "claims_history_agent":     os.getenv("MODEL_CLAIMS",     "claude-haiku-4-5-20251001"),
    "hazard_evaluation_agent":  os.getenv("MODEL_HAZARD",     "claude-sonnet-4-6"),
    "underwriting_risk_agent":  os.getenv("MODEL_RISK",       "claude-sonnet-4-6"),
    "governance_agent":         os.getenv("MODEL_GOVERNANCE", "claude-sonnet-4-6"),
    "pricing_agent":            os.getenv("MODEL_PRICING",    "claude-haiku-4-5-20251001"),
}


def model_for(agent_name: str) -> str:
    if agent_name not in MODEL_FOR_AGENT:
        raise ValueError(f"No model configured for agent: {agent_name!r}")
    return MODEL_FOR_AGENT[agent_name]
