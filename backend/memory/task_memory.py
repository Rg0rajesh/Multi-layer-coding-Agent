# backend/memory/task_memory.py
"""
Tier 1 — Task Memory (short-term).

Scoped to a single task run: current file being edited, recent errors,
test failures. Lives in one ChromaDB collection shared by every task, but
every read/write and the final wipe are scoped by task_id via metadata
filtering — there's no per-task collection, that'd be a lot of churn for
Chroma to manage over a long-running server.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import chromadb

from config import settings

logger = logging.getLogger(__name__)

_client: chromadb.HttpClient | None = None


def get_chroma_client() -> chromadb.HttpClient:
    """Shared across task_memory and project_memory — one connection pool,
    not one per tier."""
    global _client
    if _client is None:
        parsed = urlparse(settings.chroma_url)
        _client = chromadb.HttpClient(host=parsed.hostname or "localhost", port=parsed.port or 8000)
    return _client


class TaskMemory:
    """Build one of these per task_id. Cheap to construct — the real cost is
    the network calls, which all go through asyncio.to_thread since the
    chromadb client is sync."""

    COLLECTION_NAME = "task_memory"

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._collection = get_chroma_client().get_or_create_collection(self.COLLECTION_NAME)

    async def note_current_file(self, file_path: str, content_summary: str) -> None:
        await self._remember("current_file", content_summary, file_path=file_path)

    async def note_error(self, message: str, *, file_path: str | None = None) -> None:
        await self._remember("error", message, file_path=file_path or "")

    async def note_test_failure(self, test_name: str, reason: str) -> None:
        await self._remember("test_failure", reason, test_name=test_name)

    async def recall(self, query: str, kind: str | None = None, n_results: int = 5) -> list[dict[str, Any]]:
        where = {"task_id": self.task_id} if kind is None else {"task_id": self.task_id, "kind": kind}

        def _query() -> dict:
            return self._collection.query(query_texts=[query], n_results=n_results, where=where)

        try:
            raw = await asyncio.to_thread(_query)
        except Exception:
            logger.warning("Task memory recall failed for %s", self.task_id, exc_info=True)
            return []
        return _flatten(raw)

    async def clear(self) -> None:
        """Called once the task finishes. Tier 1 is explicitly disposable —
        anything worth keeping should already be in curated_memory by then."""
        try:
            await asyncio.to_thread(self._collection.delete, where={"task_id": self.task_id})
        except Exception:
            logger.warning("Failed to clear task memory for %s", self.task_id, exc_info=True)

    async def _remember(self, kind: str, content: str, **metadata: Any) -> None:
        doc_id = f"{self.task_id}:{kind}:{datetime.now(timezone.utc).timestamp()}"

        def _add() -> None:
            self._collection.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[{"task_id": self.task_id, "kind": kind, **metadata}],
            )

        try:
            await asyncio.to_thread(_add)
        except Exception:
            # Memory is an enhancement, not a hard dependency — a Chroma
            # hiccup shouldn't take down the Coder/Tester loop.
            logger.warning("Failed to write task memory (%s) for %s", kind, self.task_id, exc_info=True)


def _flatten(raw: dict) -> list[dict[str, Any]]:
    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    return [{"content": doc, **(meta or {})} for doc, meta in zip(docs, metas)]