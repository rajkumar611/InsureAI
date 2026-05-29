"""
Run the document ingestion agent against a sample document.

Usage:
    uv run python scripts/run_ingestion.py
    uv run python scripts/run_ingestion.py high_risk
    uv run python scripts/run_ingestion.py missing_fields
    uv run python scripts/run_ingestion.py prompt_injection
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

SAMPLES = {
    "harbour_fresh":    "samples/documents/property_submission_harbour_fresh.txt",
    "high_risk":        "samples/documents/property_submission_high_risk.txt",
    "missing_fields":   "samples/documents/property_submission_missing_fields.txt",
    "prompt_injection": "samples/documents/property_submission_prompt_injection.txt",
}


async def main(sample_name: str = "harbour_fresh") -> None:
    # Import here so .env is loaded before anything else
    from underwriting.pipeline.document_ingestion_agent.agent import run
    from underwriting.platform.database.connection import AsyncSessionLocal

    if sample_name not in SAMPLES:
        print(f"Unknown sample: {sample_name!r}")
        print(f"Available: {list(SAMPLES)}")
        sys.exit(1)

    doc_path = Path(SAMPLES[sample_name])
    document_content = doc_path.read_text(encoding="utf-8")
    submission_id = f"SUB-DEMO-{sample_name.upper()}-001"

    print(f"\n{'='*60}")
    print(f"  Document Ingestion Agent")
    print(f"  Sample    : {sample_name}")
    print(f"  Submission: {submission_id}")
    print(f"{'='*60}\n")

    async with AsyncSessionLocal() as session:
        result = await run(
            submission_id=submission_id,
            class_of_business="property",
            document_content=document_content,
            session=session,
        )
        await session.commit()

    print("RESULT:")
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    print(f"\nConfidence  : {result.extraction_confidence}")
    print(f"Missing     : {result.missing_required_fields}")
    print(f"Anomalies   : {result.anomalies}")


if __name__ == "__main__":
    sample = sys.argv[1] if len(sys.argv) > 1 else "harbour_fresh"
    asyncio.run(main(sample))
