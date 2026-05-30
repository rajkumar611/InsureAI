from contextlib import asynccontextmanager
import os
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
from api.routers import submissions, health, pipeline
from api.middleware.logging import log_requests
from pipeline_agents.claims_history_agent.agent import cleanup_encoder


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_workflow(_db_settings.DATABASE_URL)
    yield
    await cleanup_encoder()
    await close_workflow()
    await engine.dispose()


app = FastAPI(
    title="INSUREAI",
    description="Enterprise multi-agent AI underwriting system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: restrict to frontend origin (env var or localhost for dev)
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(log_requests)

app.include_router(health.router, tags=["health"])
app.include_router(submissions.router, prefix="/api/v1", tags=["submissions"])
app.include_router(pipeline.router, prefix="/api/v1", tags=["pipeline"])
