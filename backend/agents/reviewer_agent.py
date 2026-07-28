
"""
Reviewer — final quality gate. Runs after Tester and Security so it has
their output to weigh in on, not just the raw code.
"""
from __future__ import annotations

import logging

from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are REVIEWER, the senior code reviewer for AGENTX.
RULES:
- Score 0.0-10.0, identify issues by severity, be constructive
OUTPUT: {"score": 8.7, "summary": "...", "issues": [...], "strengths": [...],
         "approval": "approved|approved_with_suggestions|needs_revision"}
"""

APPROVAL_THRESHOLD = 6.0


async def reviewer_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "REVIEWER", "TASK", "→", "Reviewing code quality")

    user_prompt = (
        f"Files:\n{state.get('code_files', {})}\n\n"
        f"Test results: {state.get('test_results', {})}\n"
        f"Security findings: {state.get('safety_report', {})}"
    )

    try:
        review = await generate_json(system=SYSTEM_PROMPT, user=user_prompt)
    except LLMGenerationError as exc:
        await emit_log(task_id, "REVIEWER", "ERROR", "✗", f"Review failed: {exc}")
        raise

    score = review.get("score", 0)
    await emit_log(
        task_id, "REVIEWER", "PASS", "✓" if score >= APPROVAL_THRESHOLD else "⚠",
        f"Score {score}/10 — {review.get('approval', 'needs_revision')}",
    )

    return {"review_output": review, "messages": [{"agent": "REVIEWER", "content": review}]}