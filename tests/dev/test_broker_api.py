"""
Test Phase 1 API: Broker submitting a document via API key authentication.
Usage: uv run python tests/dev/test_broker_api.py
"""
import asyncio
import httpx
import json
from pathlib import Path

# Test configuration
API_BASE_URL = "http://localhost:8081"
BROKER_API_KEY = "sk-broker-001-acme-test-key-2026"
SAMPLE_DOC_PATH = "samples/documents/clean_auto_approve.txt"


async def read_sample_document() -> str:
    """Read a sample broker document."""
    doc_path = Path(SAMPLE_DOC_PATH)
    if not doc_path.exists():
        print(f"[ERROR] Sample document not found: {doc_path}")
        return ""
    return doc_path.read_text()


async def test_broker_submission() -> None:
    """Test broker submitting a document."""
    print("=" * 70)
    print("PHASE 1 TEST: Broker API Authentication & Document Submission")
    print("=" * 70)
    print()

    # Step 1: Read sample document
    print("[STEP 1] Reading sample broker document...")
    document_content = await read_sample_document()
    if not document_content:
        return
    print(f"  Document size: {len(document_content)} characters")
    print()

    # Step 2: Prepare request
    print("[STEP 2] Preparing API request...")
    headers = {
        "X-API-Key": BROKER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "document_content": document_content,
        "class_of_business": "property",
        "jurisdiction": "NZ",
    }
    print(f"  API Key: {BROKER_API_KEY}")
    print(f"  Class of Business: property")
    print(f"  Jurisdiction: NZ")
    print()

    # Step 3: Send request
    print("[STEP 3] Sending POST request to /api/v1/submissions/pipeline...")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/submissions/pipeline",
                headers=headers,
                json=payload,
            )

        print(f"  Status Code: {response.status_code}")
        print()

        if response.status_code != 200:
            print(f"[ERROR] Request failed:")
            print(f"  {response.text}")
            return

        # Parse response
        result = response.json()
        submission_id = result.get("submission_id")
        submission_ref = result.get("submission_ref")
        workflow_status = result.get("workflow_status")

        print("[STEP 4] Response received:")
        print(f"  Submission ID: {submission_id}")
        print(f"  Submission Ref: {submission_ref}")
        print(f"  Workflow Status: {workflow_status}")
        print()

        # Step 5: Display results
        print("[STEP 5] Pipeline Results:")
        print()

        if result.get("risk_assessment"):
            print("  Risk Assessment:")
            ra = result["risk_assessment"]
            print(f"    Risk Decision: {ra.get('risk_decision')}")
            print(f"    Risk Score: {ra.get('risk_score', 'N/A'):.2f}")
            print(f"    Confidence: {ra.get('confidence_score', 'N/A'):.2f}")
            print()

        if result.get("pricing_output"):
            print("  Pricing Output:")
            pricing = result["pricing_output"]
            print(f"    Base Premium: {pricing.get('base_premium', 'N/A')}")
            print(f"    Loadings: {pricing.get('loadings', [])}")
            print()

        if result.get("governance_decision"):
            print("  Governance Decision:")
            gov = result["governance_decision"]
            print(f"    Final Status: {gov.get('final_status', 'N/A')}")
            print(f"    Compliance: {gov.get('compliance_passed', 'N/A')}")
            print()

        # Step 6: Show audit trail
        print("[STEP 6] Fetching audit trail...")
        async with httpx.AsyncClient() as client:
            audit_response = await client.get(
                f"{API_BASE_URL}/api/v1/audit/{submission_id}",
                headers=headers,
            )

        if audit_response.status_code == 200:
            audit_entries = audit_response.json()
            print(f"  Total audit entries: {len(audit_entries)}")
            for i, entry in enumerate(audit_entries, 1):
                print(f"    {i}. {entry.get('agent_name')}: {entry.get('event_type')}")
        print()

        print("[SUCCESS] Test completed successfully!")
        print()
        print(f"Save this submission ID for future queries: {submission_id}")

    except httpx.ConnectError:
        print("[ERROR] Could not connect to API server")
        print("  Make sure FastAPI is running: uv run python backend/run.py")
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        raise


async def main() -> None:
    """Entry point."""
    await test_broker_submission()


if __name__ == "__main__":
    asyncio.run(main())
