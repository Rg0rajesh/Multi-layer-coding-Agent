
# backend/main.py
"""
AGENTX API entry point. Owns app wiring only — routers hold the actual
endpoint logic, services/agents/workflow hold everything else. Keeping
this file thin is deliberate: it's the one module every test and every
deployment path imports, so it shouldn't be where anyone goes looking
for business logic.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from routers import agents, auth, tasks, websocket
from services import llm_service
from services.task_service import TaskNotFoundError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the coder model up front so the first real task doesn't eat a
    # cold-start penalty on top of its own timeout budget.
    await llm_service.ensure_model_ready(settings.ollama_model)
    yield
    await llm_service.close_client()


app = FastAPI(
    title="AGENTX API",
    version="2.1.0",
    lifespan=lifespan,
)

# Frontend runs on :3000 in dev (see docker-compose.yml); nginx fronts both
# in front of a real deployment, but CORS still needs to allow the dev
# server directly for local work.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
app.include_router(websocket.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}