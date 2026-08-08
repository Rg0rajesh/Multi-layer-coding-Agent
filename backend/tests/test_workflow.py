# backend/tests/test_workflow.py
"""
Routing is the part of the workflow most likely to break silently — get
a threshold comparison backwards and a task loops forever or bails one
retry too early. These are plain function calls against fake state
dicts, so there's no LangGraph, no LLM, no DB in the loop.
"""
from __future__ import annotations

from langgraph.graph import END

from workflow.routing import route_after_human, route_after_security, route_after_tester
from workflow.workflow import build_agentx_graph


class TestRouteAfterHuman:
    def test_approved_plan_goes_to_coder(self):
        state = {"plan_approved": True, "replan_count": 0}
        assert route_after_human(state, max_replans=3) == "coder"

    def test_rejected_plan_goes_back_to_planner(self):
        state = {"plan_approved": False, "replan_count": 1}
        assert route_after_human(state, max_replans=3) == "planner"

    def test_gives_up_after_max_replans(self):
        state = {"plan_approved": False, "replan_count": 3}
        assert route_after_human(state, max_replans=3) == END


class TestRouteAfterTester:
    def test_passing_tests_move_to_security(self):
        state = {"tests_passed": True, "coder_retries": 0}
        assert route_after_tester(state, max_coder_retries=3) == "security"

    def test_failures_send_back_to_coder(self):
        state = {"tests_passed": False, "coder_retries": 1}
        assert route_after_tester(state, max_coder_retries=3) == "coder"

    def test_gives_up_after_max_retries(self):
        state = {"tests_passed": False, "coder_retries": 3}
        assert route_after_tester(state, max_coder_retries=3) == END


class TestRouteAfterSecurity:
    def test_clean_scan_moves_to_reviewer(self):
        state = {"safety_passed": True, "coder_retries": 0}
        assert route_after_security(state, max_coder_retries=3) == "reviewer"

    def test_blocking_findings_send_back_to_coder(self):
        state = {"safety_passed": False, "coder_retries": 0}
        assert route_after_security(state, max_coder_retries=3) == "coder"

    def test_gives_up_after_max_retries(self):
        state = {"safety_passed": False, "coder_retries": 3}
        assert route_after_security(state, max_coder_retries=3) == END


def test_agentx_graph_compiles():
    # Smoke test — if a node name typo breaks an edge in the real 10-node
    # pipeline, we find out here, not several agents deep into an actual run.
    assert build_agentx_graph() is not None