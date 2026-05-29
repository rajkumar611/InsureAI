"""
Eval runner — submits each sample document through the live API and scores the results.

Usage:
    uv run python evals/run_evals.py
    uv run python evals/run_evals.py --api http://localhost:8081
    uv run python evals/run_evals.py --save          # saves results to evals/results/

Requires the API server to be running (uv run uvicorn main:app --port 8081).
These are NOT pytest tests — they make real LLM calls. Run before deploying prompt changes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from evals.scenarios import SCENARIOS  # noqa: E402 — after sys.path insert

SAMPLES_DIR = Path(__file__).parent.parent / "samples" / "documents"
RESULTS_DIR = Path(__file__).parent / "results"

_PASS = "✅ PASS"
_FAIL = "❌ FAIL"
_SKIP = "⚠️  SKIP"

TIMEOUT = 300  # seconds — full pipeline can take 2-3 min


# ── Assertion helpers ─────────────────────────────────────────────────────────

def _check(scenario: dict, response: dict) -> list[str]:
    """Return list of failure messages. Empty list = all checks passed."""
    failures: list[str] = []
    s = scenario

    # Workflow status
    actual_status = response.get("workflow_status")
    if actual_status != s["expected_workflow_status"]:
        failures.append(
            f"workflow_status: expected '{s['expected_workflow_status']}', got '{actual_status}'"
        )

    # Decline reason
    if s["expected_decline_reason"]:
        actual_reason = response.get("decline_reason")
        if actual_reason != s["expected_decline_reason"]:
            failures.append(
                f"decline_reason: expected '{s['expected_decline_reason']}', got '{actual_reason}'"
            )

    # Missing fields
    for field in s.get("expected_missing_fields", []):
        if field not in (response.get("missing_critical_fields") or []):
            failures.append(f"missing_critical_fields: expected '{field}' to be listed")

    # Injection snippets
    if s["expected_injection"]:
        if not response.get("injection_snippets"):
            failures.append("injection_snippets: expected non-empty list, got empty/None")

    # Pricing presence
    if s["must_have_pricing"] and not response.get("pricing_output"):
        failures.append("pricing_output: expected to be present, got None")
    if not s["must_have_pricing"] and response.get("pricing_output"):
        failures.append("pricing_output: expected absent for non-completed pipeline, got data")

    # Governance presence
    if s["must_have_governance"] and not response.get("governance_decision"):
        failures.append("governance_decision: expected to be present, got None")

    # Risk assessment absent (early-exit cases)
    if s["must_not_have_risk"] and response.get("risk_assessment"):
        failures.append("risk_assessment: expected absent (early exit), got data — agents ran when they should not have")

    # Risk decision (when risk assessment should be present)
    if s.get("risk_decision") and not s["must_not_have_risk"]:
        ra = response.get("risk_assessment") or {}
        actual_decision = ra.get("risk_decision")
        if actual_decision != s["risk_decision"]:
            failures.append(
                f"risk_decision: expected '{s['risk_decision']}', got '{actual_decision}'"
            )

    # Pricing sanity (when pricing is present)
    po = response.get("pricing_output")
    if po:
        final = po.get("final_premium", 0)
        excess = po.get("excess_recommended", 0)
        if excess > final:
            failures.append(f"pricing: excess {excess} > final_premium {final}")
        if excess > 0 and excess % 100 != 0:
            failures.append(f"pricing: excess {excess} is not a multiple of 100")

    return failures


# ── Runner ────────────────────────────────────────────────────────────────────

def run_evals(api_base: str, save: bool) -> int:
    """Returns number of failed scenarios."""
    client = httpx.Client(timeout=TIMEOUT)

    rows: list[dict] = []
    passed = failed = skipped = 0

    print(f"\n{'─' * 72}")
    print(f"  INSUREAI Evals  |  API: {api_base}")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'─' * 72}\n")

    for i, scenario in enumerate(SCENARIOS, 1):
        doc_path = SAMPLES_DIR / scenario["doc"]
        label = f"[{i}/{len(SCENARIOS)}] {scenario['description']}"

        if not doc_path.exists():
            print(f"{_SKIP}  {label}")
            print(f"         Document not found: {doc_path}\n")
            skipped += 1
            rows.append({"scenario": scenario["description"], "status": "SKIP", "failures": [], "response": None})
            continue

        print(f"  ▶  {label}")
        document_content = doc_path.read_text(encoding="utf-8")

        try:
            resp = client.post(
                f"{api_base}/submissions/pipeline",
                json={
                    "class_of_business": scenario["class_of_business"],
                    "jurisdiction": scenario["jurisdiction"],
                    "document_content": document_content,
                },
            )
            if not resp.is_success:
                try:
                    detail = resp.json().get("detail", resp.text[:300])
                except Exception:
                    detail = resp.text[:300]
                print(f"{_FAIL}  {label}")
                print(f"         HTTP {resp.status_code}: {detail}\n")
                failed += 1
                rows.append({"scenario": scenario["description"], "status": "FAIL", "failures": [f"HTTP {resp.status_code}: {detail}"], "response": None})
                continue

            response = resp.json()
        except Exception as exc:
            print(f"{_FAIL}  {label}")
            print(f"         Connection error: {exc}\n")
            failed += 1
            rows.append({"scenario": scenario["description"], "status": "FAIL", "failures": [str(exc)], "response": None})
            continue

        failures = _check(scenario, response)

        if failures:
            print(f"{_FAIL}  {label}")
            for f in failures:
                print(f"         → {f}")
            print()
            failed += 1
            rows.append({"scenario": scenario["description"], "status": "FAIL", "failures": failures, "response": response})
        else:
            wf = response.get("workflow_status", "?")
            ref = response.get("submission_ref", "")
            print(f"{_PASS}  {label}")
            print(f"         workflow_status={wf}  ref={ref}\n")
            passed += 1
            rows.append({"scenario": scenario["description"], "status": "PASS", "failures": [], "response": response})

    total = passed + failed + skipped
    print(f"{'─' * 72}")
    print(f"  Results: {passed}/{total} passed  |  {failed} failed  |  {skipped} skipped")
    score_pct = round(passed / max(total - skipped, 1) * 100)
    print(f"  Score:   {score_pct}%")
    print(f"{'─' * 72}\n")

    if save:
        RESULTS_DIR.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = RESULTS_DIR / f"eval_{ts}.json"
        out_path.write_text(
            json.dumps({"timestamp": ts, "api_base": api_base, "score_pct": score_pct, "passed": passed, "failed": failed, "skipped": skipped, "scenarios": rows}, indent=2),
            encoding="utf-8",
        )
        print(f"  Results saved to {out_path}\n")

    return failed


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run INSUREAI evals")
    parser.add_argument("--api", default=os.getenv("API_BASE", "http://localhost:8081/api/v1"), help="API base URL")
    parser.add_argument("--save", action="store_true", help="Save results to evals/results/")
    args = parser.parse_args()

    failed_count = run_evals(api_base=args.api, save=args.save)
    sys.exit(1 if failed_count > 0 else 0)
