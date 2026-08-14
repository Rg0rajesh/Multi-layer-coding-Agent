# backend/memory/developer_memory.py
"""
Tier 3 — Developer Profile Memory (long-term).

Coding style, preferred libraries, and review feedback are keyed by user_id.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlparse

import redis.asyncio as redis
from mem0 import Memory

from config import settings

logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 5 * 60
_memory_client: Memory | None = None
_redis: redis.Redis | None = None


def _mem0_config() -> dict:
    parsed = urlparse(settings.chroma_url)
    return {
        "vector_store": {"provider": "chroma", "config": {"host": parsed.hostname or "localhost", "port": parsed.port or 8000, "collection_name": "developer_memory"}},
        "llm": {"provider": "ollama", "config": {"model": settings.ollama_model, "ollama_base_url": settings.ollama_url}},
        "embedder": {"provider": "ollama", "config": {"model": "nomic-embed-text", "ollama_base_url": settings.ollama_url}},
    }


def _get_mem0() -> Memory:
    global _memory_client
    if _memory_client is None:
        _memory_client = Memory.from_config(_mem0_config())
    return _memory_client


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _memory_text(entry: Any) -> str:
    """Mem0 releases may return dict entries or plain strings."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return str(entry.get("memory") or entry.get("text") or "")
    return str(entry) if entry is not None else ""


class DeveloperMemory:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._cache_key = f"dev_memory:{user_id}"

    async def get_profile(self) -> dict:
        cached = await self._read_cache()
        if cached is not None:
            return cached

        def _fetch() -> list[Any]:
            return _get_mem0().get_all(filters={"user_id": self.user_id})

        try:
            entries = await asyncio.to_thread(_fetch)
        except Exception:
            logger.warning("Mem0 lookup failed for user %s, falling back to empty profile", self.user_id, exc_info=True)
            return {}

        profile = {"preferences": [text for e in entries if (text := _memory_text(e))]}
        await self._write_cache(profile)
        return profile

    async def remember(self, observation: str) -> None:
        def _add() -> None:
            _get_mem0().add(observation, user_id=self.user_id)

        try:
            await asyncio.to_thread(_add)
        except Exception:
            logger.warning("Failed to store developer memory for %s", self.user_id, exc_info=True)
            return
        await self._invalidate_cache()

    async def _read_cache(self) -> dict | None:
        try:
            raw = await _get_redis().get(self._cache_key)
        except (redis.ConnectionError, redis.TimeoutError):
            return None
        return json.loads(raw) if raw else None

    async def _write_cache(self, profile: dict) -> None:
        try:
            await _get_redis().set(self._cache_key, json.dumps(profile), ex=CACHE_TTL_SECONDS)
        except (redis.ConnectionError, redis.TimeoutError):
            pass

    async def _invalidate_cache(self) -> None:
        try:
            await _get_redis().delete(self._cache_key)
        except (redis.ConnectionError, redis.TimeoutError):
            pass
