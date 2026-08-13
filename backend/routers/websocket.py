# backend/routers/websocket.py
"""Authenticated live log/event streaming for a running task."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import settings
from database import async_session_factory
from models.task import Task
from services.auth_service import decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter()
CHANNEL_PREFIX = "agentx:task:"
AUTH_TIMEOUT_SECONDS = 5
_redis: redis.Redis | None = None


def _channel(task_id: str) -> str:
    return f"{CHANNEL_PREFIX}{task_id}"


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def publish_log(task_id: str, agent_name: str, level: str, icon: str, message: str) -> None:
    await _publish(task_id, {
        "type": "log", "agent": agent_name, "level": level, "icon": icon,
        "message": message, "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def publish_event(task_id: str, payload: dict) -> None:
    await _publish(task_id, {"type": "event", "timestamp": datetime.now(timezone.utc).isoformat(), **payload})


async def _publish(task_id: str, payload: dict) -> None:
    try:
        await _get_redis().publish(_channel(task_id), json.dumps(payload))
    except (redis.ConnectionError, redis.TimeoutError):
        logger.warning("Live update dropped for task %s (Redis unreachable)", task_id, exc_info=True)


async def _authenticate_task(websocket: WebSocket, task_id: str) -> bool:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        message = json.loads(raw)
        if not isinstance(message, dict) or message.get("type") != "auth" or not message.get("token"):
            return False
        user_id = decode_access_token(message["token"])
    except (asyncio.TimeoutError, WebSocketDisconnect, json.JSONDecodeError, TypeError, AttributeError):
        return False
    except Exception:
        return False

    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None or str(task.user_id) != str(user_id):
            return False
    return True


@router.websocket("/ws/task/{task_id}")
async def task_stream(websocket: WebSocket, task_id: str):
    await websocket.accept()

    if not await _authenticate_task(websocket, task_id):
        await websocket.close(code=1008, reason="Unauthorized task stream")
        return

    pubsub = _get_redis().pubsub()
    await pubsub.subscribe(_channel(task_id))
    forward = asyncio.create_task(_forward_redis_to_client(pubsub, websocket))
    watch = asyncio.create_task(_wait_for_disconnect(websocket))

    try:
        await asyncio.wait({forward, watch}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        forward.cancel()
        watch.cancel()
        await pubsub.unsubscribe(_channel(task_id))
        await pubsub.aclose()


async def _forward_redis_to_client(pubsub: redis.client.PubSub, websocket: WebSocket) -> None:
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            await websocket.send_text(message["data"])
        except Exception:
            return


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
