
# workflow/patterns/parallel.py
"""
Tester and Security don't read each other's output — they both just react
to whatever Coder wrote. Running them side by side after Coder cuts that
stage's wall-clock time down to whichever one is slower, instead of paying
for both back to back.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.coder_agent import coder_node
from agents.human_agent import human_approval_node
from agents.planner_agent import planner_node
from agents.reviewer_agent import reviewer_node
from agents.security_agent import security_node
from agents.tester_agent import tester_node
from workflow.state import WorkflowState


async def _quality_gate(state: WorkflowState) -> dict:
    """Pure join point. LangGraph won't fire the conditional edge after this
    node until both Tester and Security have written their results into
    state — that rendezvous is this node's only job."""
    return {}


def build_parallel_graph(*, max_replans: int = 3, max_coder_retries: int = 3):
    def route_after_human(state: WorkflowState) -> str:
        if state.get("plan_approved"):
            return "coder"
        if state.get("replan_count", 0) >= max_replans:
            return END
        return "planner"

    def route_after_quality_gate(state: WorkflowState) -> str:
        if state.get("tests_passed") and state.get("safety_passed"):
            return "reviewer"
        if state.get("coder_retries", 0) >= max_coder_retries:
            return END
        return "coder"

    graph = StateGraph(WorkflowState)

    graph.add_node("planner", planner_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("coder", coder_node)
    graph.add_node("tester", tester_node)
    graph.add_node("security", security_node)
    graph.add_node("quality_gate", _quality_gate)
    graph.add_node("reviewer", reviewer_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "human_approval")
    graph.add_conditional_edges(
        "human_approval", route_after_human,
        {"coder": "coder", "planner": "planner", END: END},
    )

    # Fan out — both start as soon as Coder finishes.
    graph.add_edge("coder", "tester")
    graph.add_edge("coder", "security")

    # Fan in — quality_gate waits for both.
    graph.add_edge("tester", "quality_gate")
    graph.add_edge("security", "quality_gate")

    graph.add_conditional_edges(
        "quality_gate", route_after_quality_gate,
        {"reviewer": "reviewer", "coder": "coder", END: END},
    )
    graph.add_edge("reviewer", END)

    return graph.compile()