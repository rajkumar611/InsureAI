"""
Pipeline progress tracking for UI real-time updates.

Each workflow node calls set_step() when it starts.
The polling endpoint reads from here so the UI can show which agent is running.
Keyed by submission_id (same as LangGraph thread_id).

CURRENT STATUS (MVP):
  - Stores progress in process memory (dict)
  - Works fine for single-process deployment (uvicorn with 1 worker)
  - Data is lost on server restart (acceptable for <5min pipelines)
  - NOT suitable for multi-worker deployments (gunicorn, Kubernetes)

FUTURE IMPROVEMENT (Phase 4+):
  - Migrate to Redis with 10-minute TTL
  - Allows progress tracking across multiple workers
  - Survives server restarts

  Implementation sketch:
    import aioredis
    _redis = None

    async def init_progress_tracker(redis_url: str):
        global _redis
        _redis = await aioredis.create_redis_pool(redis_url)

    async def set_step(submission_id: str, step: str) -> None:
        if _redis:
            await _redis.setex(f"progress:{submission_id}", 600, step)
        else:
            _store[submission_id] = step

    async def cleanup_progress_tracker():
        if _redis:
            _redis.close()
            await _redis.wait_closed()
"""
from __future__ import annotations

# In-memory fallback for single-process deployments
_store: dict[str, str] = {}


def set_step(submission_id: str, step: str) -> None:
    """Record which pipeline step is currently executing."""
    _store[submission_id] = step


def get_step(submission_id: str) -> str | None:
    """Retrieve the current pipeline step for a submission."""
    return _store.get(submission_id)


def clear(submission_id: str) -> None:
    """Clear progress tracking for completed/failed submissions."""
    _store.pop(submission_id, None)
