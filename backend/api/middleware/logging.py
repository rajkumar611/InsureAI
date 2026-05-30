import json
import logging
import time
import uuid
from datetime import datetime, timezone
from starlette.requests import Request

logger = logging.getLogger("insureai.api")


class JSONFormatter(logging.Formatter):
    def format(self, record):
        return record.getMessage()


def _setup_json_logger():
    if logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


_setup_json_logger()


async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.time()

    response = await call_next(request)

    broker_id = getattr(request.state, "broker_id", None)
    latency_ms = int((time.time() - start_time) * 1000)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "broker_id": str(broker_id) if broker_id else None,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "latency_ms": latency_ms,
    }

    logger.info(json.dumps(log_entry))
    response.headers["X-Request-ID"] = request_id

    return response
