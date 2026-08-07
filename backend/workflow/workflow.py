# backend/workflow/workflow.py
"""
Builds and runs the full 10-node AGENTX pipeline (v2.1):

  Guardrail -> Planner -> Grounding -> Human -> Identity Broker
    -> Coder -> Tester -> Security -> Reviewer -> Context Curator

Every node function already existed in agents/*.py — this file's only job
is wiring them into one compiled StateGraph and knowing how to turn a
task_id into an initial state, and a finished state back into rows in
Postgres. This is what celery_worker.py imports at call time
(`from workflow.workflow import run_task_workflow`) — before this file
existed, every task submission would fail the moment a worker picked it
up.
"""
from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from agents.coder_agent import coder_node
from agents.context_curator import context_curator_node
from agents.grounding_agent import grounding_node
from agents.guardrail_agent import guardrail_node
from agents.human_agent import human_approval_node
from agents.identity_broker import identity_broker_node
from agents.planner_agent import planner_node
from agents.reviewer_agent import reviewer_node
from agents.security_agent import security_node
from agents.tester_agent import tester_node
from database import async_session_factory
from memory.memory_manager import MemoryManager
from models.code_output import CodeOutput
from models.task import Task
from workflow.routing import route_after_human, route_after_security, route_after_tester
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

MAX_REPLANS = 3
MAX_CODER_RETRIES = 3


# ---------------------------------------------------------------------------
# Routing — reuses the v1 rules from workflow/routing.py where the decision
# is identical, only remaps where v2 inserts a new node in between.
# ---------------------------------------------------------------------------

def _route_after_guardrail(state: WorkflowState) -> str:
    return END if state.get("risk_verdict") == "block" else "planner"


def _route_after_human_v2(state: WorkflowState) -> str:
    # Same approve/reject/replan decision as v1 — an approved plan just
    # needs a scoped credential (Identity Broker) before Coder can run.
    decision = route_after_human(state, max_replans=MAX_REPLANS)
    return "identity_broker" if decision == "coder" else decision


def _route_after_tester(state: WorkflowState) -> str:
    return route_after_tester(state, max_coder_retries=MAX_CODER_RETRIES)


def _route_after_security(state: WorkflowState) -> str:
    return route_after_security(state, max_coder_retries=MAX_CODER_RETRIES)


def build_agentx_graph():
    graph = StateGraph(WorkflowState)

    graph.add_node("guardrail", guardrail_node)
    graph.add_node("planner", planner_node)
    graph.add_node("grounding", grounding_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("identity_broker", identity_broker_node)
    graph.add_node("coder", coder_node)
    graph.add_node("tester", tester_node)
    graph.add_node("security", security_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("context_curator", context_curator_node)

    graph.set_entry_point("guardrail")
    graph.add_conditional_edges("guardrail", _route_after_guardrail, {"planner": "planner", END: END})

    graph.add_edge("planner", "grounding")

    # Ungrounded plans still go to a human rather than auto-replanning —
    # a person should see the unsupported_claims flag and decide (see
    # grounding_agent.py's docstring for the reasoning).
    graph.add_edge("grounding", "human_approval")

    graph.add_conditional_edges(
        "human_approval", _route_after_human_v2,
        {"identity_broker": "identity_broker", "planner": "planner", END: END},
    )
    graph.add_edge("identity_broker", "coder")
    graph.add_edge("coder", "tester")

    graph.add_conditional_edges(
        "tester", _route_after_tester, {"security": "security", "coder": "coder", END: END},
    )
    graph.add_conditional_edges(
        "security", _route_after_security, {"reviewer": "reviewer", "coder": "coder", END: END},
    )
    graph.add_edge("reviewer", "context_curator")
    graph.add_edge("context_curator", END)

    return graph.compile()


# Compiled once per worker process, not once per task — building the graph
# is cheap but there's no reason to redo it on every single job.
_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_agentx_graph()
    return _compiled_graph


# ---------------------------------------------------------------------------
# task_id  <->  WorkflowState
# ---------------------------------------------------------------------------

async def _load_initial_state(task_id: str) -> tuple[WorkflowState, Task]:
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        state: WorkflowState = {
            "task_id": str(task.id),
            "task_description": task.description or task.title,
            "language": task.language or "python",
            "project_id": str(task.project_id) if task.project_id else None,
            "user_id": str(task.user_id),
            "code_files": {},
            "plan_approved": False,
            "coder_retries": 0,
            "replan_count": 0,
            "human_interventions": 0,
            "messages": [],
        }
        return state, task


async def _persist_final_state(task_id: str, final_state: dict) -> None:
    """Folds whatever the graph ended up with back into the tasks row —
    without this, evaluation/metrics.py has nothing but zeros to read —
    and writes out code_outputs so the Code Output page has something to
    show once a run finishes."""
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return

        test_results = final_state.get("test_results") or {}
        review = final_state.get("review_output") or {}
        safety = final_state.get("safety_report") or {}
        code_files = final_state.get("code_files") or {}

        task.coder_retries = final_state.get("coder_retries", task.coder_retries)
        task.replan_count = final_state.get("replan_count", task.replan_count)
        task.human_interventions = final_state.get("human_interventions", task.human_interventions)
        task.safety_issues_found = len(safety.get("findings", []))
        task.test_count = test_results.get("total", task.test_count)
        task.tests_passed = test_results.get("passed", task.tests_passed)
        task.total_lines_written = sum(content.count("\n") + 1 for content in code_files.values())
        if review.get("score") is not None:
            task.review_score = review["score"]

        # Don't duplicate rows on a re-run of the same task_id.
        already_written = {
            row[0] for row in (
                await db.execute(select(CodeOutput.file_path).where(CodeOutput.task_id == task_id))
            ).all()
        }
        for file_path, content in code_files.items():
            if file_path in already_written:
                continue
            db.add(CodeOutput(
                task_id=task_id,
                file_path=file_path,
                file_name=file_path.rsplit("/", 1)[-1],
                content=content,
                language=task.language,
                line_count=content.count("\n") + 1,
                is_test_file="test" in file_path.lower(),
            ))

        await db.commit()


async def run_task_workflow(task_id: str) -> dict:
    """Entry point celery_worker.py calls. Runs the whole pipeline for one
    task, writes the result back to Postgres, and clears Tier-1 memory now
    that the task is finished."""
    state, task = await _load_initial_state(task_id)
    graph = _get_graph()

    final_state = await graph.ainvoke(state)
    await _persist_final_state(task_id, final_state)

    if task.project_id:
        memory = MemoryManager(task_id=task_id, user_id=str(task.user_id), project_id=str(task.project_id))
        await memory.finalize_task()

    return {
        "task_id": task_id,
        "risk_verdict": final_state.get("risk_verdict"),
        "plan_approved": final_state.get("plan_approved"),
        "tests_passed": final_state.get("tests_passed"),
        "safety_passed": final_state.get("safety_passed"),
        "review_score": (final_state.get("review_output") or {}).get("score"),
        "curated_items": len(final_state.get("curated_items", [])),
    }