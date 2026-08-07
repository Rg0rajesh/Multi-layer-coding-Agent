# backend/main.py
"""
AGENTX API entry point. Owns app wiring only — routers hold the actual
endpoint logic, services/agents/workflow hold everything else. Keeping
this file thin is deliberate: it's the one module every test and every
deployment path imports, so it shouldn't be where anyone goes looking
for business logic.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import side effect only: registers every ORM class on the shared
# declarative registry before any request comes in. Without this, a
# string-based relationship like Task.risk_score -> "SessionRiskScore"
# won't resolve unless some router happened to import that specific
# model module first — easy to break by accident, so we guarantee it
# here instead of relying on import order elsewhere.
import models  # noqa: F401

from config import settings
from routers import agents, auth, logs, outputs, profile, settings as settings_router, tasks, team, websocket
from services import llm_service
from services.task_service import TaskNotFoundError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm both local models up front so the first real task doesn't eat
    # a cold-start penalty on top of its own timeout budget. Guardrail
    # runs before Planner on every task, so it needs to be ready just as
    # much as the coder model does — firing both warm-ups together instead
    # of one after another roughly halves this wait on a fresh container.
    warmups = [
        llm_service.ensure_model_ready(settings.ollama_model),
        llm_service.ensure_model_ready(settings.llama_guard_model),
    ]
    results = await asyncio.gather(*warmups, return_exceptions=True)
    for model, result in zip((settings.ollama_model, settings.llama_guard_model), results):
        if isinstance(result, Exception):
            logger.warning("Model warm-up failed for %s — will retry on first real request", model)

    yield

    await llm_service.close_client()


app = FastAPI(
    title="AGENTX API",
    version="2.1.0",
    lifespan=lifespan,
)

# Dev default covers the Vite server (docker-compose.yml). Anything beyond
# localhost — staging, prod behind nginx.conf — comes from CORS_ORIGINS
# as a comma-separated env var, so shipping a new domain never needs a
# code change here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(TaskNotFoundError)
async def task_not_found_handler(request: Request, exc: TaskNotFoundError) -> JSONResponse:
    # Routers already catch this in most places and raise HTTPException
    # directly — this is the safety net for anywhere that doesn't.
    return JSONResponse(status_code=404, content={"detail": f"Task {exc.task_id} not found"})


app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(outputs.router)
app.include_router(logs.router)
app.include_router(team.router)
app.include_router(profile.router)
app.include_router(settings_router.router)
app.include_router(websocket.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}