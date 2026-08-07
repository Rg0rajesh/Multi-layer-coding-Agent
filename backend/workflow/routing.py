# backend/workflow/routing.py
"""
Routing decisions shared by every workflow pattern (sequential, parallel,
event-driven). This used to be copy-pasted as closures inside each pattern
file — three places to update if a retry limit ever changes, and no way
to unit test it without actually running a graph. Pulled out here so
there's one source of truth and something pytest can call directly.
"""
from __future__ import annotations

from langgraph.graph import END

from workflow.state import WorkflowState


def route_after_human(state: WorkflowState, *, max_replans: int) -> str:
    if state.get("plan_approved"):
        return "coder"
    if state.get("replan_count", 0) >= max_replans:
        return END
    return "planner"


def route_after_tester(state: WorkflowState, *, max_coder_retries: int) -> str:
    if state.get("tests_passed"):
        return "security"
    if state.get("coder_retries", 0) >= max_coder_retries:
        return END
    return "coder"


def route_after_security(state: WorkflowState, *, max_coder_retries: int) -> str:
    if state.get("safety_passed"):
        return "reviewer"
    if state.get("coder_retries", 0) >= max_coder_retries:
        return END
    return "coder"