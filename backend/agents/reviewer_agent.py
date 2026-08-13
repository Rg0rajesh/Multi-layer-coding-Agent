"""
Reviewer — final quality gate. It evaluates code after Tester and Security,
but deterministic workflow facts override an optimistic model approval.
"""
from __future__ import annotations

import logging

from memory.memory_manager import MemoryManager
from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are REVIEWER, the senior code reviewer for AGENTX.
RULES:
- Score 0.0-10.0 and identify issues by severity
- Never approve code when tests failed or security has blocking findings
- Consider the supplied project memory and known bugs
OUTPUT: {"score": 8.7, "summary": "...", "issues": [], "strengths": [],
         "approval": "approved|approved_with_suggestions|needs_revision"}
"""

APPROVAL_THRESHOLD = 6.0


async def reviewer_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "REVIEWER", "TASK", "→", "Reviewing code quality")

    memory_block = ""
    if state.get("user_id"):
        try:
            manager = MemoryManager(
                task_id=task_id,
                user_id=state["user_id"],
                project_id=state.get("project_id"),
            )
            memory_block = (await manager.build_agent_context(state.get("task_description", ""))).as_prompt_block()
        except Exception:
            logger.warning("Reviewer memory retrieval failed for task %s", task_id, exc_info=True)

    user_prompt = (
        f"Files:\n{state.get('code_files', {})}\n\n"
        f"Test results:\n{state.get('test_results', {})}\n\n"
        f"Security findings:\n{state.get('safety_report', {})}\n\n"
        f"Relevant memory:\n{memory_block or 'None'}"
    )

    try:
        review = await generate_json(system=SYSTEM_PROMPT, user=user_prompt, temperature=0.0)
    except LLMGenerationError as exc:
        await emit_log(task_id, "REVIEWER", "ERROR", "✗", f"Review failed: {exc}")
        raise

    try:
        score = max(0.0, min(10.0, float(review.get("score", 0))))
    except (TypeError, ValueError):
        score = 0.0

    test_results = state.get("test_results") or {}
    tests_failed = bool(test_results.get("failed", 0) or test_results.get("error"))
    security_failed = not state.get("safety_passed", True)

    deterministic_blockers = []
    if tests_failed:
        deterministic_blockers.append("tests_failed")
    if security_failed:
        deterministic_blockers.append("security_findings")
    if not state.get("code_files"):
        deterministic_blockers.append("no_generated_code")

    if deterministic_blockers:
        approval = "needs_revision"
        score = min(score, APPROVAL_THRESHOLD - 0.01)
    else:
        approval = review.get("approval", "needs_revision")
        if score < APPROVAL_THRESHOLD:
            approval = "needs_revision"

    review = {
        **review,
        "score": round(score, 2),
        "approval": approval,
        "deterministic_blockers": deterministic_blockers,
    }

    await emit_log(
        task_id,
        "REVIEWER",
        "PASS" if not deterministic_blockers else "WARN",
        "✓" if approval != "needs_revision" else "⚠",
        f"Score {score:.2f}/10 — {approval}",
    )

    return {"review_output": review, "messages": [{"agent": "REVIEWER", "content": review}]}
