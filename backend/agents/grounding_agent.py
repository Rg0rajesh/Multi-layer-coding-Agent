"""
Grounding agent — validates the Planner's claims against repository state
before Human approval. Grounding is a safety signal, so infrastructure
failures fail closed instead of silently declaring an ungrounded plan safe.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from database import async_session_factory
from memory.task_memory import get_chroma_client
from models.agent_run import AgentRun
from models.code_output import CodeOutput
from models.curated_memory import CuratedMemory
from models.task import Task
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

MAX_SUPPORTING_DISTANCE = 0.45
SCRATCH_COLLECTION_PREFIX = "grounding_scratch_"


@dataclass
class GroundingResult:
    grounded: bool
    unsupported_claims: list[dict] = field(default_factory=list)


async def grounding_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "GROUNDING", "TASK", "→", "Checking plan against repo state")

    claims = _extract_claims(state.get("plan") or {})
    if not claims:
        result = GroundingResult(False, [{"claim": "Plan contains no verifiable subtasks", "reason": "empty_plan"}])
        await _persist_grounding_run(task_id, result)
        await emit_log(task_id, "GROUNDING", "ERROR", "✗", "Plan has no verifiable subtasks")
        return {"grounded": False, "unsupported_claims": result.unsupported_claims}

    facts = await _read_repo_state(state.get("project_id"))
    result = await _check_grounding(claims, facts)

    if result.grounded:
        await emit_log(task_id, "GROUNDING", "PASS", "✓", "Plan checks out against repo state")
    else:
        await emit_log(task_id, "GROUNDING", "WARN", "■", f"{len(result.unsupported_claims)} unsupported claim(s) found")

    await _persist_grounding_run(task_id, result)
    return {"grounded": result.grounded, "unsupported_claims": result.unsupported_claims}


async def _persist_grounding_run(task_id: str, result: GroundingResult) -> None:
    async with async_session_factory() as db:
        db.add(AgentRun(
            task_id=task_id,
            agent_name="GROUNDING",
            agent_color="#00C896",
            status="completed" if result.grounded else "failed",
            output_data={"grounded": result.grounded, "unsupported_claims": result.unsupported_claims},
        ))
        await db.commit()


def _extract_claims(plan: dict) -> list[dict]:
    claims = []
    for subtask in plan.get("subtasks", []):
        if not isinstance(subtask, dict):
            continue
        file_path = subtask.get("file")
        description = subtask.get("description") or subtask.get("title") or ""
        if file_path and description:
            claims.append({"text": f"{description} ({file_path})", "file": _normalize_path(file_path)})
        elif description:
            claims.append({"text": description, "file": None})
    return claims


@dataclass
class RepoFacts:
    file_paths: list[str] = field(default_factory=list)
    known_notes: list[str] = field(default_factory=list)
    last_test_summary: str | None = None


async def _read_repo_state(project_id: str | None) -> RepoFacts:
    if project_id is None:
        return RepoFacts()

    async with async_session_factory() as db:
        file_rows = await db.execute(
            select(CodeOutput.file_path)
            .join(Task, Task.id == CodeOutput.task_id)
            .where(Task.project_id == project_id)
            .distinct()
        )
        note_rows = await db.execute(select(CuratedMemory.summary).where(CuratedMemory.project_id == project_id))
        last_task = await db.scalar(
            select(Task)
            .where(Task.project_id == project_id, Task.status == "completed")
            .order_by(Task.completed_at.desc())
            .limit(1)
        )

    return RepoFacts(
        file_paths=[_normalize_path(row[0]) for row in file_rows.all() if row[0]],
        known_notes=[row[0] for row in note_rows.all() if row[0]],
        last_test_summary=(
            f"Last run: {last_task.tests_passed}/{last_task.test_count} tests passing"
            if last_task is not None else None
        ),
    )


async def _check_grounding(claims: list[dict], facts: RepoFacts) -> GroundingResult:
    existing_paths = set(facts.file_paths)
    unsupported: list[dict] = []
    semantic_claims: list[dict] = []

    for claim in claims:
        path = claim.get("file")
        if path:
            if path in existing_paths:
                semantic_claims.append(claim)
            elif _looks_like_new_file(claim["text"]):
                continue
            else:
                unsupported.append({"claim": claim["text"], "reason": "referenced_file_not_found", "file": path})
        else:
            semantic_claims.append(claim)

    documents = [*facts.file_paths, *facts.known_notes]
    if facts.last_test_summary:
        documents.append(facts.last_test_summary)

    if semantic_claims and not documents:
        unsupported.extend({"claim": c["text"], "reason": "no_repo_evidence"} for c in semantic_claims)
        return GroundingResult(grounded=not unsupported, unsupported_claims=unsupported)

    if semantic_claims:
        try:
            semantic_result = await asyncio.to_thread(_score_claims, semantic_claims, documents)
        except Exception as exc:
            logger.error("Grounding infrastructure failed for plan", exc_info=True)
            semantic_result = GroundingResult(False, [{"reason": "grounding_service_error", "error": str(exc)}])
        unsupported.extend(semantic_result.unsupported_claims)

    return GroundingResult(grounded=not unsupported, unsupported_claims=unsupported)


def _score_claims(claims: list[dict], documents: list[str]) -> GroundingResult:
    client = get_chroma_client()
    collection_name = f"{SCRATCH_COLLECTION_PREFIX}{uuid.uuid4().hex}"
    collection = client.create_collection(collection_name)
    try:
        collection.add(ids=[str(i) for i in range(len(documents))], documents=documents)
        unsupported = []
        for claim in claims:
            result = collection.query(query_texts=[claim["text"]], n_results=1)
            distances = result.get("distances", [[]])[0]
            best_distance = distances[0] if distances else float("inf")
            if best_distance > MAX_SUPPORTING_DISTANCE:
                unsupported.append({
                    "claim": claim["text"],
                    "closest_distance": round(best_distance, 3),
                    "reason": "semantic_evidence_below_threshold",
                })
        return GroundingResult(grounded=not unsupported, unsupported_claims=unsupported)
    finally:
        client.delete_collection(collection_name)


_NEW_FILE_HINTS = re.compile(r"\b(create|add|new|implement)\b", re.IGNORECASE)


def _looks_like_new_file(claim_text: str) -> bool:
    return bool(_NEW_FILE_HINTS.search(claim_text))


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")
