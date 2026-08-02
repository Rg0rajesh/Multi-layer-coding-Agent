"""
Human agent (C3) — the human is a formal node, not just a viewer of the
final output. Three responsibilities:
  1. Pause the workflow at the plan-approval checkpoint until someone
     approves, edits, or rejects it.
  2. Let a person inject a brand-new agent role mid-workflow — the part
     no other system in the comparison table supports.
  3. Hand off both of the above to the API layer (routers/agents.py)
     without needing to know anything about HTTP.

Caveat that matters once this stops running as a single process: both
`_pending` and `_role_queue` below are plain in-memory dicts. That's fine
while the FastAPI app and the Celery worker share memory (dev, or a
single combined container), but the moment they're split across separate
containers — which docker-compose.yml already does — neither approvals
nor role requests submitted through the API will reach a workflow running
in the Celery process. Swap both for Redis-backed structures before that
split matters in practice.
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


# Keyed by task_id, lives in worker memory. See module docstring.
_pending: dict[str, PendingApproval] = {}

# Queued dynamic-role requests, keyed by task_id. See module docstring.
_role_queue: dict[str, list[dict]] = {}


# ---------------------------------------------------------------------------
# Plan approval
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Dynamic role assignment
# ---------------------------------------------------------------------------

def add_dynamic_role(state: WorkflowState, role_name: str, role_config: dict) -> dict:
    """Applies a role addition directly to workflow state. Used when the
    orchestrator itself drives the addition (e.g. replaying queued
    requests between nodes) rather than reading straight off the queue."""
    dynamic_roles = [*state.get("dynamic_roles", []), {"role": role_name, "config": role_config}]
    logger.info("Dynamic role '%s' requested for task %s", role_name, state["task_id"])
    return {"dynamic_roles": dynamic_roles}


def queue_dynamic_role(task_id: str, role_name: str, config: dict, reason: str | None) -> None:
    """Called from the API layer when a human asks for a new agent mid-run.
    Doesn't touch workflow state directly — the router doesn't have access
    to a live WorkflowState, only a task_id — so this just parks the
    request until the orchestrator checks in."""
    _role_queue.setdefault(task_id, []).append(
        {"role": role_name, "config": config, "reason": reason}
    )


def drain_dynamic_roles(task_id: str) -> list[dict]:
    """Orchestrator calls this between nodes to pick up anything queued
    since the last check, then folds each entry into state via
    add_dynamic_role(). Empties the queue on read so nothing gets
    applied twice."""
    return _role_queue.pop(task_id, [])