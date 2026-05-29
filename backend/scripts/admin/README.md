# Admin Scripts

One-time setup and utility scripts for database administration and data seeding.

## Scripts

- **`check_db.py`** — Quick health check of database connectivity and row counts
  ```bash
  python scripts/admin/check_db.py
  ```

- **`seed_data.py`** — Load initial test data (customers, claims, embeddings, regulations)
  ```bash
  python scripts/admin/seed_data.py
  ```

- **`seed_brokers.py`** — Create test broker accounts and API keys (Phase 1)
  ```bash
  python scripts/admin/seed_brokers.py
  ```

## When to Run

1. After `alembic upgrade head` — run `seed_data.py`
2. After database setup — run `check_db.py` to verify
3. Before Phase 1 testing — run `seed_brokers.py`

## Important

These scripts modify the database. Use only in **development/local environments**.
Never run in production.
