from contextlib import asynccontextmanager
import sys
from pathlib import Path

# Add parent (root) and current (backend) to sys.path
backend_path = Path(__file__).parent
root_path = backend_path.parent
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(backend_path))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.connection import engine, _settings as _db_settings
from engine.orchestration.workflow import init_workflow, close_workflow
from database.init_schema import check_and_init_schema
from api.routers import submissions, health, pipeline
from api.middleware import authenticate_api_key
from api.middleware.logging import log_requests
from api.middleware.rate_limiter import check_rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    await check_and_init_schema()
    await init_workflow(_db_settings.DATABASE_URL)
    yield
    await close_workflow()
    await engine.dispose()


app = FastAPI(
    title="INSUREAI",
    description="Enterprise multi-agent AI underwriting system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(check_rate_limit)
app.middleware("http")(authenticate_api_key)
app.middleware("http")(log_requests)

app.include_router(health.router, tags=["health"])
app.include_router(submissions.router, prefix="/api/v1", tags=["submissions"])
app.include_router(pipeline.router, prefix="/api/v1", tags=["pipeline"])
