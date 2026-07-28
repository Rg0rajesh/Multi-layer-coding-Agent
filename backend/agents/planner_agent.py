
"""
Planner — turns a task description into an ordered list of subtasks the
Coder can work through one at a time.
"""
from __future__ import annotations

import logging

from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

MAX_SUBTASKS = 8

SYSTEM_PROMPT = f"""You are PLANNER, the task decomposition expert for AGENTX.
RULES:
- Output ONLY valid JSON, no markdown, no explanations
- Maximum {MAX_SUBTASKS} subtasks per task
- Identify which files need to be created or modified
- Estimate total time in minutes
OUTPUT: {{"task_summary": "...", "estimated_minutes": 5, "complexity": "low|medium|high",
         "subtasks": [{{"id": 1, "title": "...", "file": "...", "description": "...", "agent": "CODER"}}]}}
"""


async def planner_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    is_replan = state.get("replan_count", 0) > 0

    await emit_log(
        task_id, "PLANNER", "INIT", "→",
        "Re-planning after human feedback" if is_replan else "Breaking task into subtasks",
    )

    try:
        plan = await generate_json(system=SYSTEM_PROMPT, user=_build_prompt(state))
    except LLMGenerationError as exc:
        await emit_log(task_id, "PLANNER", "ERROR", "✗", f"Couldn't produce a usable plan: {exc}")
        raise

    plan["subtasks"] = plan.get("subtasks", [])[:MAX_SUBTASKS]

    await emit_log(
        task_id, "PLANNER", "PASS", "✓",
        f"Plan ready — {len(plan['subtasks'])} subtask(s), est. {plan.get('estimated_minutes', '?')} min",
    )

    return {
        "plan": plan,
        "plan_approved": False,  # human hasn't seen this version yet
        "messages": [{"agent": "PLANNER", "content": plan}],
    }


def _build_prompt(state: WorkflowState) -> str:
    parts = [f"Task: {state['task_description']}", f"Language: {state.get('language') or 'unspecified'}"]
    if state.get("replan_count"):
        parts.append("This is a re-plan — the previous version was rejected. Don't just repeat it.")
    return "\n".join(parts)