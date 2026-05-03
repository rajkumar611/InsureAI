from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qbe_underwriting.platform.database.connection import engine
from qbe_underwriting.platform.database.models import Base
from qbe_underwriting.api.routers import submissions, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="QBE AI Underwriting",
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
