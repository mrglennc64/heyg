"""AvatarForge gateway — FastAPI entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forge_shared.storage import ensure_bucket

from .db import engine
from .models import Base
from .routers import avatars, generate, voices


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ensure_bucket()
    yield
    await engine.dispose()


app = FastAPI(
    title="AvatarForge",
    version="0.1.0",
    description="Open-source avatar video generation: XTTS v2 + LivePortrait/"
                "SadTalker + MuseTalk behind a HeyGen-style scene-graph API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router)
app.include_router(voices.router)
app.include_router(avatars.router)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}
