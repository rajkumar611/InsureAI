import asyncio
from datetime import datetime, timedelta, timezone
from starlette.requests import Request
from starlette.responses import JSONResponse


DAILY_LIMIT = 10
_rate_store: dict[str, dict] = {}
_locks: dict[str, asyncio.Lock] = {}


async def _get_lock(broker_id: str) -> asyncio.Lock:
    if broker_id not in _locks:
        _locks[broker_id] = asyncio.Lock()
    return _locks[broker_id]


def _should_skip(request: Request) -> bool:
    path = request.url.path
    if path.startswith("/health"):
        return True
    if not path.startswith("/api/v1"):
        return True
    return False


async def check_rate_limit(request: Request, call_next):
    if _should_skip(request):
        return await call_next(request)

    broker_id = getattr(request.state, "broker_id", None)
    if not broker_id:
        return await call_next(request)

    now = datetime.now(timezone.utc)
    midnight_utc = now.replace(hour=0, minute=0, second=0, microsecond=0)

    lock = await _get_lock(broker_id)
    async with lock:
        entry = _rate_store.get(broker_id, {})
        reset_at = entry.get("reset_at")

        if reset_at is None or reset_at <= now:
            _rate_store[broker_id] = {"count": 0, "reset_at": midnight_utc + timedelta(days=1)}
            entry = _rate_store[broker_id]

        if entry["count"] >= DAILY_LIMIT:
            reset_time = entry["reset_at"].isoformat()
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "limit": f"{DAILY_LIMIT} requests/day",
                    "resets_at": reset_time,
                },
            )

        entry["count"] += 1

    response = await call_next(request)
    return response
