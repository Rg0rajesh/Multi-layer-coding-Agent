"""AGENTX FastAPI application entry point."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import models  # noqa: F401

from config import settings
from routers import agents, auth, evaluation, logs, outputs, profile, settings as settings_router, tasks, team, websocket
from services import llm_service
from services.task_service import TaskNotFoundError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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


app = FastAPI(title="AGENTX API", version="2.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(TaskNotFoundError)
async def task_not_found_handler(request: Request, exc: TaskNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": f"Task {exc.task_id} not found"})


app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(agents.router)
app.include_router(outputs.router)
app.include_router(logs.router)
app.include_router(evaluation.router)
app.include_router(team.router)
app.include_router(profile.router)
app.include_router(settings_router.router)
app.include_router(websocket.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
