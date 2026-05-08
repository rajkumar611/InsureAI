from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from underwriting.platform.database.connection import engine, _settings as _db_settings
from underwriting.platform.database.models import Base
from underwriting.platform.orchestration.workflow import init_workflow, close_workflow
from underwriting.api.routers import submissions, health, pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_workflow(_db_settings.DATABASE_URL)
    yield
    await close_workflow()
    await engine.dispose()


app = FastAPI(
    title="AI Underwriting System",
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

app.include_router(health.router, tags=["health"])
app.include_router(submissions.router, prefix="/api/v1", tags=["submissions"])
app.include_router(pipeline.router, prefix="/api/v1", tags=["pipeline"])
