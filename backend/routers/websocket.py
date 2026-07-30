
# backend/routers/websocket.py
"""
Live log/event streaming for a running task.

Celery workers and the FastAPI app are separate processes (and under
docker-compose, possibly separate containers) — there's no shared memory
to push a websocket message through directly. Redis pub/sub bridges that:
whatever generates a log line (agents running inside Celery, via
services/log_service.py) publishes it to a per-task channel, and whichever
websocket connection is watching that task picks it up from there.

Each connection gets its own Redis subscription rather than routing
through a shared in-process "connection manager." That avoids needing any
locking or shared state on this side — Redis already fans a channel out
to every subscriber, so there's nothing left for us to reimplement.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

CHANNEL_PREFIX = "agentx:task:"

_redis: redis.Redis | None = None


def _channel(task_id: str) -> str:
    return f"{CHANNEL_PREFIX}{task_id}"


def _get_redis() -> redis.Redis:
    # Lazy singleton — same idea as the Ollama client in llm_service.py.
    # redis-py's connection pool is already safe to share across coroutines.
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Publish side — called from agents (via log_service) and workflow nodes
# ---------------------------------------------------------------------------

async def publish_log(task_id: str, agent_name: str, level: str, icon: str, message: str) -> None:
    await _publish(task_id, {
        "type": "log",
        "agent": agent_name,
        "level": level,
        "icon": icon,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def publish_event(task_id: str, payload: dict) -> None:
    await _publish(task_id, {
        "type": "event",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    })


async def _publish(task_id: str, payload: dict) -> None:
    try:
        await _get_redis().publish(_channel(task_id), json.dumps(payload))
    except (redis.ConnectionError, redis.TimeoutError):
        # The log line already made it to Postgres via log_service — losing
        # the live push isn't worth failing whatever agent step triggered it.
        logger.warning("Live update dropped for task %s (Redis unreachable)", task_id, exc_info=True)


# ---------------------------------------------------------------------------
# Subscribe side — one websocket connection per browser tab
# ---------------------------------------------------------------------------

@router.websocket("/ws/task/{task_id}")
async def task_stream(websocket: WebSocket, task_id: str):
    await websocket.accept()

    pubsub = _get_redis().pubsub()
    await pubsub.subscribe(_channel(task_id))

    forward = asyncio.create_task(_forward_redis_to_client(pubsub, websocket))
    watch = asyncio.create_task(_wait_for_disconnect(websocket))

    try:
        # Whichever finishes first — Redis stream ends (shouldn't happen)
        # or the client hangs up — we tear the whole thing down.
        await asyncio.wait({forward, watch}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        forward.cancel()
        watch.cancel()
        await pubsub.unsubscribe(_channel(task_id))
        await pubsub.aclose()


async def _forward_redis_to_client(pubsub: redis.client.PubSub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue  # subscribe/unsubscribe confirmations, not actual payloads
        try:
            await websocket.send_text(message["data"])
        except Exception:
            return  # client's gone — let the outer wait() notice and clean up


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    try:
        while True:
            # The frontend doesn't need to send anything here — this just
            # parks on the socket so a closed tab is caught immediately
            # instead of only surfacing on the next failed send.
            await websocket.receive_text()
    except WebSocketDisconnect:
        return