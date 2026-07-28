
"""
Human agent (C3) — the human is a formal node, not just a viewer of the
final output. Two responsibilities:
  1. Pause the workflow at the plan-approval checkpoint until someone
     approves, edits, or rejects it.
  2. Let a person inject a brand-new agent role mid-workflow — the part
     no other system in the comparison table supports.

The actual approve/reject/add-role calls arrive over the API
(routers/agents.py — not built yet). This module owns the waiting and the
state transitions; it doesn't know about HTTP.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SECONDS = 30 * 60
Decision = Literal["approve", "reject", "edit"]


@dataclass
class PendingApproval:
    future: asyncio.Future
    plan: dict


# Keyed by task_id, lives in worker memory. Fine for a single Celery worker;
# swap for a Redis-backed wait before running more than one worker process.
_pending: dict[str, PendingApproval] = {}


async def human_approval_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    plan = state.get("plan", {})
    await emit_log(task_id, "HUMAN", "TASK", "→", "Waiting on plan approval")

    loop = asyncio.get_running_loop()
    approval = PendingApproval(future=loop.create_future(), plan=plan)
    _pending[task_id] = approval

    try:
        decision, payload = await asyncio.wait_for(approval.future, timeout=APPROVAL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await emit_log(task_id, "HUMAN", "ERROR", "✗", "No response within the approval window")
        return {"plan_approved": False}
    finally:
        _pending.pop(task_id, None)

    interventions = state.get("human_interventions", 0) + 1

    if decision == "approve":
        await emit_log(task_id, "HUMAN", "PASS", "✓", "Plan approved")
        return {"plan_approved": True, "human_interventions": interventions}

    if decision == "edit":
        await emit_log(task_id, "HUMAN", "TASK", "✎", "Plan edited by human, re-approved")
        return {"plan": payload, "plan_approved": True, "human_interventions": interventions}

    await emit_log(task_id, "HUMAN", "WARN", "✗", f"Plan rejected: {payload or 'no reason given'}")
    return {
        "plan_approved": False,
        "replan_count": state.get("replan_count", 0) + 1,
        "human_interventions": interventions,
    }


def submit_decision(task_id: str, decision: Decision, payload: dict | str | None = None) -> bool:
    """Called from the API layer when someone acts on the approval prompt.
    Returns False if nothing's actually waiting (already timed out, or
    never started)."""
    pending = _pending.get(task_id)
    if pending is None or pending.future.done():
        return False
    pending.future.set_result((decision, payload))
    return True


def add_dynamic_role(state: WorkflowState, role_name: str, role_config: dict) -> dict:
    """Records a mid-workflow 'add this agent now' request. Doesn't spin the
    agent up itself — that's the orchestrator's job once the graph is
    rebuilt — but it's what gives Project Memory a trail of who asked for
    what and why."""
    dynamic_roles = [*state.get("dynamic_roles", []), {"role": role_name, "config": role_config}]
    logger.info("Dynamic role '%s' requested for task %s", role_name, state["task_id"])
    return {"dynamic_roles": dynamic_roles}