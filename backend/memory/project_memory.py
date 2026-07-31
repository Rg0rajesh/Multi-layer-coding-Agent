# backend/memory/project_memory.py
"""
Tier 2 — Project Memory (medium-term).

Architecture decisions, API contracts, known bugs — scoped to project_id,
persists across every task run against that project.

v2 rule: this tier no longer accepts raw session logs. The only legitimate
writer is Context Curator (agents/context_curator.py), via
promote_from_curated(). If you're tempted to add a general-purpose
add_note() here, don't — that's exactly the hole v2 closed.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from memory.task_memory import get_chroma_client

logger = logging.getLogger(__name__)

VALID_TAGS = {"architectural_decision", "known_bug", "api_contract", "file_structure"}


class ProjectMemory:
    COLLECTION_NAME = "project_memory"

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._collection = get_chroma_client().get_or_create_collection(self.COLLECTION_NAME)

    async def promote_from_curated(self, item: dict[str, Any]) -> None:
        """The one write path in. `item` is Context Curator's output shape:
        {"type": "known_bug", "summary": "...", ...}. Curator already
        filtered out `transient` items before this ever gets called."""
        tag = item.get("type")
        summary = item.get("summary")

        if tag not in VALID_TAGS:
            logger.warning("Dropping curated item with unrecognised tag %r for project %s", tag, self.project_id)
            return
        if not summary:
            return

        await self._write(tag, summary, source_task_id=item.get("source_task_id", ""))

    async def recall(self, query: str, tag: str | None = None, n_results: int = 8) -> list[dict[str, Any]]:
        where = {"project_id": self.project_id} if tag is None else {"project_id": self.project_id, "tag": tag}

        def _query() -> dict:
            return self._collection.query(query_texts=[query], n_results=n_results, where=where)

        try:
            raw = await asyncio.to_thread(_query)
        except Exception:
            logger.warning("Project memory recall failed for %s", self.project_id, exc_info=True)
            return []
        return _flatten(raw)

    async def known_bugs(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Convenience wrapper — this is the recall Planner actually cares
        about most: don't re-suggest a fix that's already known to fail."""
        return await self.recall(query, tag="known_bug", n_results=n_results)

    async def _write(self, tag: str, summary: str, **metadata: Any) -> None:
        doc_id = f"{self.project_id}:{tag}:{datetime.now(timezone.utc).timestamp()}"

        def _add() -> None:
            self._collection.add(
                ids=[doc_id],
                documents=[summary],
                metadatas=[{"project_id": self.project_id, "tag": tag, **metadata}],
            )

        try:
            await asyncio.to_thread(_add)
        except Exception:
            logger.warning("Failed to promote %s into project memory for %s", tag, self.project_id, exc_info=True)


def _flatten(raw: dict) -> list[dict[str, Any]]:
    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    return [{"content": doc, **(meta or {})} for doc, meta in zip(docs, metas)]