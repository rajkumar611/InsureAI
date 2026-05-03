# Sample Documents

Simulated OCR output from broker-submitted PDFs.
Used for local development and testing — no Azure Document Intelligence key required.

| File | Scenario | Expected outcome |
|---|---|---|
| `property_submission_harbour_fresh.txt` | Clean, complete submission | `extraction_confidence: high`, ACCEPT likely |
| `property_submission_high_risk.txt` | Flood zone, repeat claims, timber construction | `extraction_confidence: high`, REFER likely |
| `property_submission_missing_fields.txt` | Sum insured and floor area missing | `extraction_confidence: low`, loopback to broker |
| `property_submission_prompt_injection.txt` | Embedded injection attempts in document body | Anomalies flagged, injection text ignored |

## Usage

```python
from pathlib import Path

doc = Path("samples/documents/property_submission_harbour_fresh.txt").read_text()
result = await run_document_ingestion_agent(
    submission_id="SUB-2025-00847",
    class_of_business="property",
    document_content=doc,
)
```
