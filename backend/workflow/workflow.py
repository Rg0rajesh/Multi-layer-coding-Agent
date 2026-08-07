
# backend/workflow/workflow.py
"""
Entry point celery_worker.py calls into. Loads the task, builds the graph
that matches its coordination_pattern, runs it, and writes the results
back to Postgres. The graph builders themselves (sequential / parallel /
event_driven) live in workflow/patterns/ — this file's only job is wiring
a DB row to a LangGraph run and back.

v2 note: this still runs the original 6-node pipeline (Planner -> Human ->
Coder -> Tester -> Security -> Reviewer). Wiring in Guardrail, Grounding,
Identity Broker and Context Curator is Step 25 in the build plan —
deliberately deferred until all four of those agents have been exercised
on their own first.
"""
from __future__ import annotations

import logging
from typing import Callable

from database import async_session_factory
from memory.memory_manager import MemoryManager
from models.code_output import CodeOutput
from models.task import Task
from workflow.patterns import build_event_driven_graph, build_parallel_graph, build_sequential_graph
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

GRAPH_BUILDERS: dict[str, Callable] = {
    "sequential": build_sequential_graph,
    "parallel": build_parallel_graph,
    "event_driven": build_event_driven_graph,
}


class TransientWorkflowError(Exception):
    """Mirrors celery_worker.TransientWorkflowError so its `except` clause
    still catches failures from here. Kept as a separate class rather than
    importing celery_worker's — that file imports this one, so importing
    back the other way would be circular."""


async def run_task_workflow(task_id: str) -> dict:
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found — was it deleted before the worker picked it up?")
        initial_state = _build_initial_state(task)

    graph = _get_graph(task.coordination_pattern)

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:  # noqa: BLE001 — let celery_worker decide retry vs. hard fail
        logger.exception("Workflow run failed for task %s", task_id)
        raise TransientWorkflowError(str(exc)) from exc

    await _persist_results(task_id, final_state)
    await _finalize_memory(task)

    return {
        "task_id": task_id,
        "plan_approved": final_state.get("plan_approved", False),
        "tests_passed": final_state.get("tests_passed", False),
        "safety_passed": final_state.get("safety_passed", False),
        "review_score": (final_state.get("review_output") or {}).get("score"),
    }


def _get_graph(pattern: str):
    builder = GRAPH_BUILDERS.get(pattern)
    if builder is None:
        logger.warning("Unknown coordination_pattern %r on this task, falling back to sequential", pattern)
        builder = build_sequential_graph
    return builder()


def _build_initial_state(task: Task) -> WorkflowState:
    return {
        "task_id": str(task.id),
        "task_description": task.description or task.title,
        "language": task.language or "python",
        "project_id": str(task.project_id) if task.project_id else None,
        "user_id": str(task.user_id),
        "code_files": {},
        "plan_approved": False,
        "safety_passed": False,
        "tests_passed": False,
        "coder_retries": 0,
        "replan_count": 0,
        "human_interventions": 0,
        "messages": [],
    }


async def _persist_results(task_id: str, state: dict) -> None:
    """Writes whatever the graph produced back onto the task row and into
    code_outputs. Deliberately tolerant — if the run bailed early (e.g. hit
    max re-plans before Coder ever touched a file), we still save what
    exists instead of failing the whole update over a missing key."""
    code_files: dict[str, str] = state.get("code_files", {})
    test_results = state.get("test_results") or {}
    safety_report = state.get("safety_report") or {}
    review_output = state.get("review_output") or {}

    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return  # task got deleted mid-run — nothing left to update

        task.replan_count = state.get("replan_count", task.replan_count)
        task.coder_retries = state.get("coder_retries", task.coder_retries)
        task.human_interventions = state.get("human_interventions", task.human_interventions)
        task.test_count = test_results.get("total", task.test_count)
        task.tests_passed = test_results.get("passed", task.tests_passed)
        task.safety_issues_found = len(safety_report.get("findings", []))
        task.total_lines_written = sum(content.count("\n") + 1 for content in code_files.values())
        if "score" in review_output:
            task.review_score = review_output["score"]

        for file_path, content in code_files.items():
            db.add(CodeOutput(
                task_id=task_id,
                file_path=file_path,
                file_name=file_path.rsplit("/", 1)[-1],
                file_type=file_path.rsplit(".", 1)[-1] if "." in file_path else None,
                content=content,
                language=task.language,
                line_count=content.count("\n") + 1,
                is_test_file="test" in file_path.lower(),
            ))

        await db.commit()


async def _finalize_memory(task: Task) -> None:
    """Wipes Tier 1 (task-scoped) memory now that the run is over. Tiers
    2/3 are untouched — this only clears what's disposable."""
    memory = MemoryManager(
        str(task.id), str(task.user_id),
        project_id=str(task.project_id) if task.project_id else None,
    )
    await memory.finalize_task()