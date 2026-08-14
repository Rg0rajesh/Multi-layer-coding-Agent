from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import chromadb
import httpx

from config import settings

logger = logging.getLogger(__name__)
_client: chromadb.HttpClient | None = None


def get_chroma_client() -> chromadb.HttpClient:
    global _client
    if _client is None:
        parsed = urlparse(settings.chroma_url)
        _client = chromadb.HttpClient(host=parsed.hostname or "localhost", port=parsed.port or 8000)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Use Ollama directly; Chroma's Ollama wrapper was producing /api/embed/api/embed."""
    url = f"{settings.ollama_url.rstrip('/')}/api/embed"
    payload = {"model": "nomic-embed-text", "input": texts}
    with httpx.Client(timeout=settings.ollama_timeout_seconds) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    embeddings = data.get("embeddings")
    if not embeddings:
        raise RuntimeError("Ollama /api/embed returned no embeddings")
    return embeddings


class TaskMemory:
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
            query_embedding = embed_texts([query])[0]
            return self._collection.query(query_embeddings=[query_embedding], n_results=n_results, where=where)

        try:
            raw = await asyncio.to_thread(_query)
        except Exception:
            logger.warning("Task memory recall failed for %s", self.task_id, exc_info=True)
            return []
        return _flatten(raw)

    async def clear(self) -> None:
        try:
            await asyncio.to_thread(self._collection.delete, where={"task_id": self.task_id})
        except Exception:
            logger.warning("Failed to clear task memory for %s", self.task_id, exc_info=True)

    async def _remember(self, kind: str, content: str, **metadata: Any) -> None:
        doc_id = f"{self.task_id}:{kind}:{datetime.now(timezone.utc).timestamp()}"

        def _add() -> None:
            embedding = embed_texts([content])[0]
            self._collection.add(ids=[doc_id], documents=[content], embeddings=[embedding], metadatas=[{"task_id": self.task_id, "kind": kind, **metadata}])

        try:
            await asyncio.to_thread(_add)
        except Exception:
            logger.warning("Failed to write task memory (%s) for %s", kind, self.task_id, exc_info=True)


def _flatten(raw: dict) -> list[dict[str, Any]]:
    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    return [{"content": doc, **(meta or {})} for doc, meta in zip(docs, metas)]
