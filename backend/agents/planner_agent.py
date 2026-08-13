"""
Planner — turns a task description into an ordered list of subtasks while
using user/project/task memory to avoid repeating known decisions and bugs.
"""
from __future__ import annotations

import logging

from memory.memory_manager import MemoryManager
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
- Respect relevant developer preferences and known project bugs/decisions
- Never claim an existing file exists unless memory/repo context supports it
OUTPUT: {{"task_summary": "...", "estimated_minutes": 5, "complexity": "low|medium|high",
         "subtasks": [{{"id": 1, "title": "...", "file": "...", "description": "...", "agent": "CODER"}}]}}
"""


async def planner_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    is_replan = state.get("replan_count", 0) > 0

    await emit_log(
        task_id,
        "PLANNER",
        "INIT",
        "→",
        "Re-planning after human feedback" if is_replan else "Breaking task into subtasks",
    )

    try:
        plan = await generate_json(system=SYSTEM_PROMPT, user=await _build_prompt(state))
    except LLMGenerationError as exc:
        logger.error("Planner LLM output was invalid JSON. Raw response: %r", exc.raw_response)
        await emit_log(task_id, "PLANNER", "ERROR", "✗", f"Couldn't produce a usable plan: {exc}")
        raise

    if not isinstance(plan, dict):
        raise LLMGenerationError("Planner returned a non-object JSON value", raw_response=str(plan))

    subtasks = plan.get("subtasks", [])
    if not isinstance(subtasks, list):
        subtasks = []
    plan["subtasks"] = subtasks[:MAX_SUBTASKS]

    await emit_log(
        task_id,
        "PLANNER",
        "PASS",
        "✓",
        f"Plan ready — {len(plan['subtasks'])} subtask(s), est. {plan.get('estimated_minutes', '?')} min",
    )

    return {
        "plan": plan,
        "plan_approved": False,
        "messages": [{"agent": "PLANNER", "content": plan}],
    }


async def _build_prompt(state: WorkflowState) -> str:
    parts = [f"Task: {state['task_description']}", f"Language: {state.get('language') or 'unspecified'}"]

    user_id = state.get("user_id")
    if user_id:
        manager = MemoryManager(
            task_id=state["task_id"],
            user_id=user_id,
            project_id=state.get("project_id"),
        )
        try:
            context = await manager.build_agent_context(state["task_description"])
            memory_block = context.as_prompt_block()
            if memory_block:
                parts.append("Relevant memory and prior project knowledge:\n" + memory_block)
        except Exception:
            logger.warning("Planner memory retrieval failed for task %s", state["task_id"], exc_info=True)

    if state.get("replan_count"):
        parts.append("This is a re-plan — the previous version was rejected. Incorporate the rejection instead of repeating it.")
        if state.get("messages"):
            parts.append(f"Recent workflow feedback:\n{state['messages'][-3:]}")

    return "\n\n".join(parts)
