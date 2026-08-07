# workflow/patterns/sequential.py
"""
Default coordination pattern — one agent at a time, in the order a human
would actually work through this: plan it, get sign-off, write it, verify
it, ship it. Coder is the retry target for both Tester and Security since
it's the only agent that can actually change the code.
"""
from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from agents.coder_agent import coder_node
from agents.human_agent import human_approval_node
from agents.planner_agent import planner_node
from agents.reviewer_agent import reviewer_node
from agents.security_agent import security_node
from agents.tester_agent import tester_node
from workflow.routing import route_after_human, route_after_security, route_after_tester
from workflow.state import WorkflowState


def build_sequential_graph(*, max_replans: int = 3, max_coder_retries: int = 3):
    graph = StateGraph(WorkflowState)

    graph.add_node("planner", planner_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("coder", coder_node)
    graph.add_node("tester", tester_node)
    graph.add_node("security", security_node)
    graph.add_node("reviewer", reviewer_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "human_approval")
    graph.add_conditional_edges(
        "human_approval", partial(route_after_human, max_replans=max_replans),
        {"coder": "coder", "planner": "planner", END: END},
    )
    graph.add_edge("coder", "tester")
    graph.add_conditional_edges(
        "tester", partial(route_after_tester, max_coder_retries=max_coder_retries),
        {"security": "security", "coder": "coder", END: END},
    )
    graph.add_conditional_edges(
        "security", partial(route_after_security, max_coder_retries=max_coder_retries),
        {"reviewer": "reviewer", "coder": "coder", END: END},
    )
    graph.add_edge("reviewer", END)

    return graph.compile()