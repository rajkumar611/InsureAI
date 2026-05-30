# Sample Documents

Simulated OCR output from broker-submitted PDFs.
Used for local development and testing — no Azure Document Intelligence key required.

| File | Scenario | Expected Workflow Status |
|---|---|---|
| `clean_auto_approve.txt` | Clean, complete submission | ACCEPTED (auto-approve) |
| `decline_missing_fields.txt` | Sum insured and floor area missing | DECLINED (missing fields) |
| `decline_prompt_injection.txt` | Embedded injection attempts in document body | DECLINED (injection flagged) |
| `referral_hazard_zone.txt` | Flood/hazard zone, high risk location | REFERRED (manual review) |
| `referral_large_claim.txt` | Large sum insured, needs underwriter review | REFERRED (manual review) |
| `referral_more_claims.txt` | Multiple claims history, pattern assessment needed | REFERRED (manual review) |
| `referral_sum_insured.txt` | Sum insured exceeds automatic approval threshold | REFERRED (manual review) |

## Usage

```python
from pathlib import Path

doc = Path("sample_broker_files/documents/clean_auto_approve.txt").read_text()
result = await run_document_ingestion_agent(
    submission_id="SUB-2025-00847",
    class_of_business="property",
    document_content=doc,
)
```
