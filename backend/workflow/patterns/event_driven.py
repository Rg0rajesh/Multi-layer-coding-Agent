
# workflow/patterns/event_driven.py
"""
Structurally identical to the sequential graph, but every node publishes a
"this agent just finished, here's what changed" event, separate from the
human-readable log lines log_service.emit_log already sends. Live Monitor
can key off these instead of parsing message text.

Scope note: this does NOT make the workflow distributed. human_agent's
approval wait is still an in-process asyncio.Future (see
agents/human_agent.py) — a task that started on one Celery worker still
has to finish on that same worker.
"""
from __future__ import annotations

import logging
from typing import Callable

from langgraph.graph import END, StateGraph

from agents.coder_agent import coder_node
from agents.human_agent import human_approval_node
from agents.planner_agent import planner_node
from agents.reviewer_agent import reviewer_node
from agents.security_agent import security_node
from agents.tester_agent import tester_node
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)


def _with_event(agent_name: str, node_fn: Callable) -> Callable:
    async def wrapped(state: WorkflowState) -> dict:
        result = await node_fn(state)
        await _publish_event(state["task_id"], agent_name, result)
        return result

    return wrapped


async def _publish_event(task_id: str, agent_name: str, result: dict) -> None:
    try:
        from routers.websocket import publish_event  # not built yet — Step 9
    except ImportError:
        return

    try:
        await publish_event(task_id, {"agent": agent_name, "keys_updated": list(result.keys())})
    except Exception:  # noqa: BLE001 — a broken event bus shouldn't kill the run
        logger.warning("Couldn't publish event for %s on task %s", agent_name, task_id, exc_info=True)


def build_event_driven_graph(*, max_replans: int = 3, max_coder_retries: int = 3):
    def route_after_human(state: WorkflowState) -> str:
        if state.get("plan_approved"):
            return "coder"
        if state.get("replan_count", 0) >= max_replans:
            return END
        return "planner"

    def route_after_tester(state: WorkflowState) -> str:
        if state.get("tests_passed"):
            return "security"
        if state.get("coder_retries", 0) >= max_coder_retries:
            return END
        return "coder"

    def route_after_security(state: WorkflowState) -> str:
        if state.get("safety_passed"):
            return "reviewer"
        if state.get("coder_retries", 0) >= max_coder_retries:
            return END
        return "coder"

    graph = StateGraph(WorkflowState)

    graph.add_node("planner", _with_event("PLANNER", planner_node))
    graph.add_node("human_approval", _with_event("HUMAN", human_approval_node))
    graph.add_node("coder", _with_event("CODER", coder_node))
    graph.add_node("tester", _with_event("TESTER", tester_node))
    graph.add_node("security", _with_event("SECURITY", security_node))
    graph.add_node("reviewer", _with_event("REVIEWER", reviewer_node))

    graph.set_entry_point("planner")
    graph.add_edge("planner", "human_approval")
    graph.add_conditional_edges(
        "human_approval", route_after_human,
        {"coder": "coder", "planner": "planner", END: END},
    )
    graph.add_edge("coder", "tester")
    graph.add_conditional_edges(
        "tester", route_after_tester,
        {"security": "security", "coder": "coder", END: END},
    )
    graph.add_conditional_edges(
        "security", route_after_security,
        {"reviewer": "reviewer", "coder": "coder", END: END},
    )
    graph.add_edge("reviewer", END)

    return graph.compile()