from __future__ import annotations

import json
import logging

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline_agents.document_ingestion_agent.schemas import SubmissionData
from pipeline_agents.hazard_evaluation_agent.schemas import HazardScore
from engine.cost_tracking.middleware import record_llm_cost
from engine.llm.client import anthropic_client, model_for
from engine.llm.parsing import extract_first_json_object
from engine.orchestration.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

AGENT_NAME = "hazard_evaluation_agent"
MAX_RETRIES = 2

# ── Deterministic scoring formulas ────────────────────────────────────────────
# LLM decides categorical hazard levels and writes rationale.
# Numeric floats are computed deterministically from those levels so that
# identical input documents always yield identical scores across every run.

_HAZARD_LEVEL_SCORE: dict[str, float] = {
    "EXTREME": 0.90, "HIGH": 0.70, "MEDIUM": 0.45, "LOW": 0.20, "NEGLIGIBLE": 0.05,
}


def _deterministic_overall_score(overall_hazard_level: str) -> float:
    return _HAZARD_LEVEL_SCORE.get(overall_hazard_level, 0.45)


def _deterministic_data_gaps(submission_data: SubmissionData) -> list[str]:
    """Compute data gaps from missing submission fields — never left to the LLM."""
    gaps: list[str] = []
    unknown = {"unknown", "not provided", "none", ""}
    if not submission_data.construction_type or submission_data.construction_type.lower() in unknown:
        gaps.append("construction_type unknown")
    if not submission_data.year_built:
        gaps.append("year_built unknown")
    if not submission_data.gross_floor_area_sqm:
        gaps.append("gross_floor_area unknown")
    if not submission_data.occupancy_type or submission_data.occupancy_type.lower() in unknown:
        gaps.append("occupancy_type unknown")
    return gaps


def _deterministic_confidence(data_gaps: list[str]) -> float:
    conf = 0.90 - len(data_gaps) * 0.05
    return round(max(0.50, min(0.95, conf)), 2)


# ── Simulated external hazard data ────────────────────────────────────────────
# In production: replace with live calls to GeoNet (NZ seismic), NIWA (NZ flood),
# local council flood maps, and AFAC (AU fire risk) APIs.

_NZ_SEISMIC: dict[str, str] = {
    "wellington": "HIGH", "wairarapa": "HIGH", "marlborough": "HIGH",
    "kaikoura": "HIGH", "gisborne": "HIGH", "queenstown": "HIGH",
    "christchurch": "MEDIUM", "napier": "MEDIUM", "hawke": "MEDIUM",
    "rotorua": "MEDIUM", "taupo": "MEDIUM",
    "auckland": "LOW", "dunedin": "LOW",
}

_NZ_FLOOD: dict[str, str] = {
    "hawke": "HIGH", "napier": "HIGH", "hastings": "HIGH",
    "whanganui": "HIGH", "westport": "HIGH", "greymouth": "HIGH",
    "auckland": "MEDIUM", "nelson": "MEDIUM", "queenstown": "MEDIUM",
    "christchurch": "MEDIUM",
}

_AU_FIRE: dict[str, str] = {
    "western australia": "HIGH", "perth": "HIGH",
    "new south wales": "HIGH", "south australia": "HIGH",
    "victoria": "HIGH", "tasmania": "HIGH",
    "queensland": "MEDIUM", "brisbane": "MEDIUM",
    "northern territory": "MEDIUM", "sydney": "MEDIUM", "melbourne": "MEDIUM",
}

_AU_FLOOD: dict[str, str] = {
    "queensland": "HIGH", "brisbane": "HIGH", "cairns": "HIGH",
    "townsville": "HIGH", "darwin": "HIGH", "northern territory": "HIGH",
    "new south wales": "MEDIUM", "victoria": "MEDIUM",
}

_CYCLONE_REGIONS = {"cairns", "townsville", "darwin", "broome", "mackay", "rockhampton"}
_COASTAL_KEYWORDS = {"marine parade", "waterfront", "beach", "coastal", "harbour", "esplanade"}
_INDUSTRIAL_KEYWORDS = {"industrial", "warehouse", "factory", "port", "wharf", "freight", "chemical", "refinery"}
_COMMERCIAL_CENTRAL_KEYWORDS = {"central", " cbd", "city centre", "queen st", "lambton quay", "victoria st"}


def _industrial_proximity(addr: str) -> str:
    a = addr.lower()
    if any(kw in a for kw in _INDUSTRIAL_KEYWORDS):
        return "HIGH — industrial or warehouse indicators present in address"
    if any(kw in a for kw in _COMMERCIAL_CENTRAL_KEYWORDS):
        return "LOW — city centre / commercial precinct; no industrial zoning expected"
    return "UNKNOWN — manual check required"


def _derive_hazard_data(risk_address: str, jurisdiction: str) -> dict:
    addr = risk_address.lower()

    def lookup(table: dict[str, str], default: str) -> str:
        for key, val in table.items():
            if key in addr:
                return val
        return default

    is_coastal = any(kw in addr for kw in _COASTAL_KEYWORDS)

    if jurisdiction == "NZ":
        seismic = lookup(_NZ_SEISMIC, "MEDIUM")
        flood = lookup(_NZ_FLOOD, "LOW")
        return {
            "source": "simulated_dev — replace with GeoNet + NIWA + council APIs in production",
            "jurisdiction": "NZ",
            "geonet_seismic_hazard_zone": seismic,
            "geonet_fault_proximity_km": 3 if seismic == "HIGH" else 15 if seismic == "MEDIUM" else 40,
            "niwa_flood_hazard_zone": flood,
            "niwa_100yr_flood_depth_m": 1.5 if flood == "HIGH" else 0.3 if flood == "MEDIUM" else 0.0,
            "council_flood_map_category": flood,
            "coastal_erosion_risk": "MEDIUM" if is_coastal else "LOW",
            "bushfire_risk": "LOW",
            "cyclone_exposure": "LOW",
            "industrial_proximity": _industrial_proximity(risk_address),
        }
    else:  # AU
        fire = lookup(_AU_FIRE, "MEDIUM")
        flood = lookup(_AU_FLOOD, "LOW")
        cyclone = "HIGH" if any(r in addr for r in _CYCLONE_REGIONS) else "LOW"
        return {
            "source": "simulated_dev — replace with AFAC + BOM + state flood APIs in production",
            "jurisdiction": "AU",
            "afac_bushfire_risk_zone": fire,
            "bom_flood_hazard": flood,
            "cyclone_design_wind_speed": "HIGH" if cyclone == "HIGH" else "STANDARD",
            "cyclone_exposure": cyclone,
            "coastal_erosion_risk": "MEDIUM" if is_coastal else "LOW",
            "seismic_hazard": "LOW",
            "industrial_proximity": _industrial_proximity(risk_address),
        }



# ── Main entry point ──────────────────────────────────────────────────────────

async def run(
    *,
    submission_id: str,
    submission_data: SubmissionData,
    class_of_business: str,
    jurisdiction: str,
    session: AsyncSession,
) -> HazardScore:
    """
    Evaluate property and environmental hazards using Claude Sonnet.

    Derives simulated external hazard data from the risk address, then
    asks the LLM to synthesise a HazardScore with per-dimension rationale.
    """
    hazard_data = _derive_hazard_data(
        risk_address=submission_data.risk_address or "",
        jurisdiction=jurisdiction,
    )

    prompt_template = PromptRegistry.load(AGENT_NAME)
    model = model_for(AGENT_NAME)

    system_prompt = prompt_template.render(
        submission_id=submission_id,
        risk_address=submission_data.risk_address or "Not provided",
        construction_type=submission_data.construction_type or "Unknown",
        year_built=str(submission_data.year_built or "Unknown"),
        occupancy_type=submission_data.occupancy_type or "Unknown",
        gross_floor_area_sqm=str(submission_data.gross_floor_area_sqm or "Unknown"),
        security_features=", ".join(submission_data.security_features) or "None declared",
        external_hazard_data=json.dumps(hazard_data, indent=2),
    )

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "hazard_evaluation_agent: attempt %d/%d  submission=%s",
            attempt, MAX_RETRIES, submission_id,
        )

        response = await anthropic_client.messages.create(
            model=model,
            max_tokens=2048,
            temperature=0,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "Evaluate the property hazards and produce the HazardScore JSON.",
                }
            ],
        )

        await record_llm_cost(
            session=session,
            response=response,
            agent_name=AGENT_NAME,
            prompt_version=str(prompt_template.version),
            class_of_business=class_of_business,
            jurisdiction=jurisdiction,
            feature_tag="hazard_evaluation",
        )

        if not response.content:
            raise ValueError("LLM returned empty response")
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(extract_first_json_object(raw))
            data["submission_id"] = submission_id
            allowed = HazardScore.model_fields.keys()
            data = {k: v for k, v in data.items() if k in allowed}
            score = HazardScore.model_validate(data)

            # Override LLM-generated floats with deterministic formulas so that
            # identical input documents always produce identical numeric outputs.
            score.data_gaps = _deterministic_data_gaps(submission_data)
            score.overall_hazard_score = _deterministic_overall_score(score.overall_hazard_level)
            score.confidence = _deterministic_confidence(score.data_gaps)

            logger.info(
                "hazard_evaluation_agent: success  overall=%s (%.2f)  confidence=%.2f",
                score.overall_hazard_level, score.overall_hazard_score, score.confidence,
            )
            return score

        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "hazard_evaluation_agent: attempt %d failed — %s: %s",
                attempt, type(exc).__name__, exc,
            )
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"hazard_evaluation_agent failed after {MAX_RETRIES} attempts "
                    f"for submission {submission_id}.\nLast error: {exc}\nResponse: {raw[:400]}"
                ) from exc
