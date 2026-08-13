"""
Context Curator — the only component allowed to promote task information into
long-term project memory. It also writes explicitly identified, reusable
coding preferences into user-scoped Tier-3 developer memory.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from database import async_session_factory
from memory.developer_memory import DeveloperMemory
from memory.project_memory import ProjectMemory
from models.curated_memory import CuratedMemory
from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are CURATOR, the memory-curation agent for AGENTX.
You receive one finished task's workflow state.

RULES:
- Tag notable events as architectural_decision, known_bug, or transient
- Only architectural_decision and known_bug items are promoted to project memory
- Be conservative; do not store secrets, credentials, raw tokens, or personal data
- Summaries must be short, factual, and reusable on future tasks
OUTPUT: {"promote": [{"type": "known_bug", "summary": "..."}]}
"""

KEEPABLE_TAGS = {"architectural_decision", "known_bug"}
SECRET_MARKERS = ("password", "secret", "api_key", "access_token", "refresh_token", "private_key", "credential")


async def context_curator_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    project_id = state.get("project_id")
    await emit_log(task_id, "CONTEXT_CURATOR", "TASK", "→", "Curating session for long-term memory")

    promotable = await _curate(task_id, project_id, state) if project_id else []
    await _persist_developer_preferences(state)

    await emit_log(task_id, "SYSTEM", "PASS", "↑", "Task finalised. All 10 agents complete.")
    return {"curated_items": promotable}


async def _curate(task_id: str, project_id: str, state: WorkflowState) -> list[dict]:
    candidates: list[dict] = []

    try:
        tagged = await generate_json(system=SYSTEM_PROMPT, user=_session_transcript(state), temperature=0.0)
        for item in tagged.get("promote", []):
            if (
                isinstance(item, dict)
                and item.get("type") in KEEPABLE_TAGS
                and isinstance(item.get("summary"), str)
                and item["summary"].strip()
            ):
                candidates.append({"type": item["type"], "summary": item["summary"].strip(), "source_task_id": task_id})
    except LLMGenerationError as exc:
        logger.warning("Curator model unavailable for task %s: %s", task_id, exc)
        await emit_log(task_id, "CONTEXT_CURATOR", "WARN", "▲", "LLM curation unavailable; deterministic facts retained")

    test_results = state.get("test_results") or {}
    if test_results.get("failed", 0) or test_results.get("error"):
        candidates.append({
            "type": "known_bug",
            "summary": f"Task ended with failing tests: {test_results.get('failures', [])[:3]}",
            "source_task_id": task_id,
        })

    if not state.get("safety_passed", True):
        report = state.get("safety_report") or {}
        candidates.append({
            "type": "known_bug",
            "summary": f"Security findings detected: {(report.get('findings') or [])[:3]}",
            "source_task_id": task_id,
        })

    promotable = _sanitize(candidates)
    await _persist(project_id, task_id, promotable)

    await emit_log(
        task_id, "CONTEXT_CURATOR", "PASS", "✓",
        f"{len(promotable)} item(s) promoted to project memory" if promotable else "Nothing worth keeping long-term this run",
    )
    return promotable


def _sanitize(items: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for item in items:
        summary = str(item.get("summary", "")).strip()
        lowered = summary.lower()
        if not summary or any(marker in lowered for marker in SECRET_MARKERS):
            continue
        key = (item["type"], lowered)
        if key in seen:
            continue
        seen.add(key)
        result.append({**item, "summary": summary[:1000]})
    return result


def _session_transcript(state: WorkflowState) -> str:
    return "\n".join(str(m) for m in state.get("messages", [])) + (
        f"\nFinal test results: {state.get('test_results', {})}"
        f"\nFinal security report: {state.get('safety_report', {})}"
    )


async def _persist(project_id: str, task_id: str, items: list[dict]) -> None:
    if not items:
        return
    async with async_session_factory() as db:
        for item in items:
            existing = await db.scalar(
                select(CuratedMemory).where(
                    CuratedMemory.project_id == project_id,
                    CuratedMemory.tag == item["type"],
                    CuratedMemory.summary == item["summary"],
                ).limit(1)
            )
            if existing:
                continue
            db.add(CuratedMemory(
                project_id=project_id,
                source_task_id=task_id,
                tag=item["type"],
                summary=item["summary"],
            ))
        await db.commit()

    project_memory = ProjectMemory(project_id)
    for item in items:
        await project_memory.promote_from_curated(item)


async def _persist_developer_preferences(state: WorkflowState) -> None:
    """Tier-3 writes are user-scoped and only come from an approved review."""
    user_id = state.get("user_id")
    review = state.get("review_output") or {}
    if not user_id or review.get("approval") == "needs_revision":
        return

    preferences = review.get("developer_preferences", [])
    if not isinstance(preferences, list):
        return

    memory = DeveloperMemory(user_id)
    for preference in preferences:
        if not isinstance(preference, str):
            continue
        clean = preference.strip()[:500]
        lowered = clean.lower()
        if not clean or any(marker in lowered for marker in SECRET_MARKERS):
            continue
        await memory.remember(f"Reusable coding preference observed: {clean}")
