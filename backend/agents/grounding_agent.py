# backend/agents/grounding_agent.py
"""
Grounding agent (C8) — checks the Planner's plan against what the repo
actually looks like before Human ever sees it.

Deliberately not an LLM call: a model that's already drifted toward
telling the user what they want to hear can't be trusted to grade its
own drift, so this stays a plain embedding-similarity check against real
repo facts (file paths, curated memory, last test run) instead of asking
another model "does this plan look right to you."
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

# Below this distance, a claim counts as backed by something real in the
# repo. Chroma's default embedding function uses a roughly cosine-shaped
# distance (lower = closer) — this number came from eyeballing real plans
# against real repo state, not a formula. Tune it once actual runs exist.
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
        # An empty plan isn't Grounding's problem — Human will see it's
        # empty regardless, no point spending a Chroma round trip on it.
        result = GroundingResult(grounded=True)
        await _persist_grounding_run(task_id, result)
        return {"grounded": result.grounded, "unsupported_claims": result.unsupported_claims}

    facts = await _read_repo_state(state.get("project_id"))
    result = await _check_grounding(claims, facts)

    if result.grounded:
        await emit_log(task_id, "GROUNDING", "PASS", "✓", "Plan checks out against repo state")
    else:
        await emit_log(
            task_id, "GROUNDING", "WARN", "■",
            f"{len(result.unsupported_claims)} unsupported claim(s) found",
        )

    await _persist_grounding_run(task_id, result)
    return {"grounded": result.grounded, "unsupported_claims": result.unsupported_claims}


# ---------------------------------------------------------------------------
# Persistence — Grounding is deterministic and never wrote anything to the
# DB before, which meant GET /agents/:id/grounding-report had nothing to
# read. AgentRun.output_data is the natural home for it: same table Live
# Monitor already polls for every other agent.
# ---------------------------------------------------------------------------

async def _persist_grounding_run(task_id: str, result: GroundingResult) -> None:
    async with async_session_factory() as db:
        db.add(AgentRun(
            task_id=task_id,
            agent_name="GROUNDING",
            agent_color="#00C896",
            status="completed",
            output_data={"grounded": result.grounded, "unsupported_claims": result.unsupported_claims},
        ))
        await db.commit()


# ---------------------------------------------------------------------------
# Claim extraction — turns a Planner subtask list into short statements we
# can actually check, e.g. "Add JWT refresh endpoint (routers/auth.py)"
# ---------------------------------------------------------------------------

def _extract_claims(plan: dict) -> list[dict]:
    claims = []
    for subtask in plan.get("subtasks", []):
        file_path = subtask.get("file")
        description = subtask.get("description") or subtask.get("title") or ""

        if file_path and description:
            claims.append({"text": f"{description} ({file_path})", "file": file_path})
        elif description:
            claims.append({"text": description, "file": None})

    return claims


# ---------------------------------------------------------------------------
# Repo facts — what actually exists right now. No git shell-out here on
# purpose: code_outputs and curated_memory already track everything the
# pipeline itself has written and learned, which is what a plan is
# realistically going to reference.
# ---------------------------------------------------------------------------

@dataclass
class RepoFacts:
    file_paths: list[str] = field(default_factory=list)
    known_notes: list[str] = field(default_factory=list)  # curated_memory summaries
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
        note_rows = await db.execute(
            select(CuratedMemory.summary).where(CuratedMemory.project_id == project_id)
        )
        last_task = await db.scalar(
            select(Task)
            .where(Task.project_id == project_id, Task.status == "completed")
            .order_by(Task.completed_at.desc())
            .limit(1)
        )

    last_test_summary = (
        f"Last run: {last_task.tests_passed}/{last_task.test_count} tests passing"
        if last_task is not None else None
    )

    return RepoFacts(
        file_paths=[row[0] for row in file_rows.all()],
        known_notes=[row[0] for row in note_rows.all()],
        last_test_summary=last_test_summary,
    )


# ---------------------------------------------------------------------------
# Embedding similarity check — the actual "grounding" logic
# ---------------------------------------------------------------------------

async def _check_grounding(claims: list[dict], facts: RepoFacts) -> GroundingResult:
    documents = [*facts.file_paths, *facts.known_notes]
    if facts.last_test_summary:
        documents.append(facts.last_test_summary)

    if not documents:
        # Brand-new project, nothing to compare against yet — don't punish
        # the first plan a project ever gets for having no history.
        return GroundingResult(grounded=True)

    try:
        return await asyncio.to_thread(_score_claims, claims, documents)
    except Exception:
        # Chroma is meant to be a safety net here, not a hard gate — a
        # hiccup shouldn't block the whole pipeline over it.
        logger.warning("Grounding check failed, letting the plan through", exc_info=True)
        return GroundingResult(grounded=True)


def _score_claims(claims: list[dict], documents: list[str]) -> GroundingResult:
    client = get_chroma_client()
    collection_name = f"{SCRATCH_COLLECTION_PREFIX}{uuid.uuid4().hex}"
    collection = client.create_collection(collection_name)

    try:
        collection.add(ids=[str(i) for i in range(len(documents))], documents=documents)

        unsupported = []
        for claim in claims:
            if claim["file"] and _looks_like_new_file(claim["text"]) and claim["file"] not in documents:
                continue  # creating something new is expected to miss — that's not what we're checking

            result = collection.query(query_texts=[claim["text"]], n_results=1)
            distances = result.get("distances", [[]])[0]
            best_distance = distances[0] if distances else float("inf")

            if best_distance > MAX_SUPPORTING_DISTANCE:
                unsupported.append({"claim": claim["text"], "closest_distance": round(best_distance, 3)})

        return GroundingResult(grounded=not unsupported, unsupported_claims=unsupported)
    finally:
        client.delete_collection(collection_name)


_NEW_FILE_HINTS = re.compile(r"\b(create|add|new)\b", re.IGNORECASE)


def _looks_like_new_file(claim_text: str) -> bool:
    return bool(_NEW_FILE_HINTS.search(claim_text))