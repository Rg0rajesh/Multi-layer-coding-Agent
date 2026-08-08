# backend/tests/test_agents.py
"""
Each agent node tested in isolation. The LLM call and the log emitter are
mocked out — these tests care about the node's own logic (merging files,
truncating subtasks, deciding pass/fail), not whether Ollama is up.

Requires pytest-asyncio with asyncio_mode = auto (or mark tests manually).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agents.coder_agent import coder_node
from agents.planner_agent import MAX_SUBTASKS, planner_node
from agents.reviewer_agent import APPROVAL_THRESHOLD, reviewer_node
from agents.security_agent import security_node
from services.llm_service import LLMGenerationError

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_logging(monkeypatch):
    """Every node logs through emit_log — patch it everywhere at once
    instead of repeating this in every test class."""
    mock = AsyncMock()
    for module in (
        "agents.planner_agent",
        "agents.coder_agent",
        "agents.reviewer_agent",
        "agents.security_agent",
    ):
        monkeypatch.setattr(f"{module}.emit_log", mock)
    return mock


class TestPlannerAgent:
    async def test_truncates_subtasks_to_max(self, monkeypatch):
        oversized_plan = {
            "task_summary": "test",
            "estimated_minutes": 10,
            "complexity": "medium",
            "subtasks": [{"id": i, "title": f"step {i}"} for i in range(MAX_SUBTASKS + 5)],
        }
        monkeypatch.setattr("agents.planner_agent.generate_json", AsyncMock(return_value=oversized_plan))

        result = await planner_node({"task_id": "t1", "task_description": "build a thing"})

        assert len(result["plan"]["subtasks"]) == MAX_SUBTASKS
        assert result["plan_approved"] is False  # human hasn't seen this version yet

    async def test_bad_model_output_bubbles_up(self, monkeypatch):
        monkeypatch.setattr(
            "agents.planner_agent.generate_json",
            AsyncMock(side_effect=LLMGenerationError("not valid json")),
        )

        with pytest.raises(LLMGenerationError):
            await planner_node({"task_id": "t1", "task_description": "build a thing"})


class TestCoderAgent:
    async def test_merges_new_files_without_clobbering_existing(self, monkeypatch):
        monkeypatch.setattr(
            "agents.coder_agent.generate_json",
            AsyncMock(return_value={"src/new.py": "print('hi')"}),
        )
        # log_tool_call hits the DB for real (it's recording against the
        # identity token) — not something this node-level test should
        # need live Postgres for. Treat every call as in-scope.
        monkeypatch.setattr("agents.coder_agent.log_tool_call", AsyncMock(return_value=True))

        state = {
            "task_id": "t1",
            "task_description": "add a helper",
            "code_files": {"src/existing.py": "x = 1"},
            "coder_retries": 0,
        }
        result = await coder_node(state)

        assert result["code_files"]["src/existing.py"] == "x = 1"
        assert result["code_files"]["src/new.py"] == "print('hi')"

    async def test_retry_counter_only_bumps_on_retry(self, monkeypatch):
        monkeypatch.setattr("agents.coder_agent.generate_json", AsyncMock(return_value={}))

        first_pass = await coder_node(
            {"task_id": "t1", "task_description": "x", "code_files": {}, "coder_retries": 0}
        )
        assert first_pass["coder_retries"] == 0  # not a retry yet

        second_pass = await coder_node({
            "task_id": "t1", "task_description": "x", "code_files": {},
            "coder_retries": 1, "test_results": {"failures": ["boom"]},
        })
        assert second_pass["coder_retries"] == 2


class TestReviewerAgent:
    async def test_score_at_threshold_is_recorded(self, monkeypatch):
        monkeypatch.setattr(
            "agents.reviewer_agent.generate_json",
            AsyncMock(return_value={"score": APPROVAL_THRESHOLD, "approval": "approved"}),
        )

        result = await reviewer_node(
            {"task_id": "t1", "code_files": {}, "test_results": {}, "safety_report": {}}
        )
        assert result["review_output"]["score"] == APPROVAL_THRESHOLD


class TestSecurityAgent:
    async def test_skips_scan_with_no_python_files(self):
        state = {"task_id": "t1", "code_files": {"src/app.ts": "console.log(1)"}}
        result = await security_node(state)

        assert result["safety_passed"] is True
        assert result["safety_report"]["findings"] == []