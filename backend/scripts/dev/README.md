# Dev & Test Scripts

Development and integration testing utilities for testing agents and API endpoints.

## Scripts

- **`run_ingestion.py`** — Test the document ingestion agent in isolation
  ```bash
  python scripts/dev/run_ingestion.py                    # default: harbour_fresh
  python scripts/dev/run_ingestion.py high_risk          # high-risk scenario
  python scripts/dev/run_ingestion.py missing_fields     # missing data scenario
  python scripts/dev/run_ingestion.py prompt_injection   # security test
  ```

- **`test_broker_api.py`** — End-to-end API test: submit document via API
  ```bash
  python scripts/dev/test_broker_api.py
  ```

## When to Use

- **Local development** — test agents without running the full workflow
- **CI/CD testing** — validate agent behavior before merging
- **Debugging** — isolate issues to specific pipeline stages

## Important

These scripts use test/demo API keys and sample documents.
They do NOT modify production state.
