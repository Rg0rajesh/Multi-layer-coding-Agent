# backend/agents/context_curator.py
"""
Context Curator (C6) — last stop before a task's session log disappears
for good. Skims the full run, tags anything worth keeping as an
architectural_decision or known_bug, and writes only those into long-term
project memory. Everything else — the back-and-forth, the false starts,
the "never mind, that worked" — gets dropped on purpose.

This is what fixes the v1 gap where known bugs kept getting rediscovered:
Tier 2 used to take writes from anywhere, so it slowly filled with noise.
Now the only door in is this one.
"""
from __future__ import annotations

import logging

from database import async_session_factory
from memory.project_memory import ProjectMemory
from models.curated_memory import CuratedMemory
from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are CURATOR, the memory-curation agent for AGENTX.
You receive one finished task's full session log.

RULES:
- Tag each notable event as architectural_decision, known_bug, or transient
- Only architectural_decision and known_bug items get returned
- Be conservative: when in doubt, tag transient rather than polluting long-term memory

OUTPUT: {"promote": [{"type": "known_bug", "summary": "..."}]}
"""

KEEPABLE_TAGS = {"architectural_decision", "known_bug"}


async def context_curator_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    project_id = state.get("project_id")

    await emit_log(task_id, "CONTEXT_CURATOR", "TASK", "→", "Curating session for long-term memory")

    # Standalone runs with no project attached have nowhere for this to
    # live — nothing wrong with the task, just nothing to curate against.
    promotable = await _curate(task_id, project_id, state) if project_id else []

    await emit_log(task_id, "SYSTEM", "PASS", "↑", "Task finalised. All 10 agents complete.")
    return {"curated_items": promotable}


async def _curate(task_id: str, project_id: str, state: WorkflowState) -> list[dict]:
    try:
        tagged = await generate_json(system=SYSTEM_PROMPT, user=_session_transcript(state))
    except LLMGenerationError as exc:
        logger.warning("Curator couldn't tag session for task %s: %s", task_id, exc)
        await emit_log(task_id, "CONTEXT_CURATOR", "WARN", "▲", "Curation skipped — model output unusable")
        return []

    promotable = [
        {**item, "source_task_id": task_id}
        for item in tagged.get("promote", [])
        if item.get("type") in KEEPABLE_TAGS and item.get("summary")
    ]

    await _persist(project_id, task_id, promotable)

    await emit_log(
        task_id, "CONTEXT_CURATOR", "PASS", "✓",
        f"{len(promotable)} item(s) promoted to project memory" if promotable
        else "Nothing worth keeping long-term this run",
    )
    return promotable


def _session_transcript(state: WorkflowState) -> str:
    # messages accumulates across every node via operator.add — closest
    # thing we have to "the full session log" the prompt asks for.
    return "\n".join(str(m) for m in state.get("messages", []))


async def _persist(project_id: str, task_id: str, items: list[dict]) -> None:
    if not items:
        return

    async with async_session_factory() as db:
        for item in items:
            db.add(CuratedMemory(
                project_id=project_id,
                source_task_id=task_id,
                tag=item["type"],
                summary=item["summary"],
            ))
        await db.commit()

    # curated_memory above is the source of truth; this is just the
    # searchable index over it. If Chroma hiccups, the Postgres rows
    # already landed — nothing here is lost, just not queryable yet.
    project_memory = ProjectMemory(project_id)
    for item in items:
        await project_memory.promote_from_curated(item)