# backend/agents/human_agent.py
"""
Human agent (C3) — the human is a formal node, not just a viewer of the
final output. Three responsibilities:
  1. Pause the workflow at the plan-approval checkpoint until someone
     approves, edits, or rejects it.
  2. Let a person inject a brand-new agent role mid-workflow.
  3. Hand off both of the above to the API layer (routers/agents.py).

Approval state is stored in Redis because FastAPI and Celery run in separate
containers/processes.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal

import redis.asyncio as redis

from config import settings
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SECONDS = 30 * 60
APPROVAL_PLAN_TTL_SECONDS = APPROVAL_TIMEOUT_SECONDS
Decision = Literal["approve", "reject", "edit"]

APPROVAL_CHANNEL_PREFIX = "agentx:approval:"
APPROVAL_PLAN_PREFIX = "agentx:approval-plan:"
ROLE_QUEUE_KEY_PREFIX = "agentx:roles:"

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _approval_channel(task_id: str) -> str:
    return f"{APPROVAL_CHANNEL_PREFIX}{task_id}"


def _approval_plan_key(task_id: str) -> str:
    return f"{APPROVAL_PLAN_PREFIX}{task_id}"


def _role_queue_key(task_id: str) -> str:
    return f"{ROLE_QUEUE_KEY_PREFIX}{task_id}"


async def human_approval_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "HUMAN", "TASK", "→", "Waiting on plan approval")

    r = _get_redis()
    plan = state.get("plan") or {}

    # Make the pending plan readable by FastAPI while the Celery worker waits.
    await r.set(
        _approval_plan_key(task_id),
        json.dumps(plan),
        ex=APPROVAL_PLAN_TTL_SECONDS,
    )

    pubsub = r.pubsub()
    await pubsub.subscribe(_approval_channel(task_id))

    try:
        decision, payload = await asyncio.wait_for(
            _wait_for_decision(pubsub), timeout=APPROVAL_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        await emit_log(task_id, "HUMAN", "ERROR", "✗", "No response within the approval window")
        await r.delete(_approval_plan_key(task_id))
        return {"plan_approved": False}
    finally:
        await pubsub.unsubscribe(_approval_channel(task_id))
        await pubsub.aclose()

    interventions = state.get("human_interventions", 0) + 1

    if decision == "approve":
        await emit_log(task_id, "HUMAN", "PASS", "✓", "Plan approved")
        await r.delete(_approval_plan_key(task_id))
        return {"plan_approved": True, "human_interventions": interventions}

    if decision == "edit":
        edited_plan = payload if isinstance(payload, dict) else plan
        await emit_log(task_id, "HUMAN", "TASK", "✎", "Plan edited by human, re-approved")
        await r.set(_approval_plan_key(task_id), json.dumps(edited_plan), ex=APPROVAL_PLAN_TTL_SECONDS)
        return {"plan": edited_plan, "plan_approved": True, "human_interventions": interventions}

    await emit_log(task_id, "HUMAN", "WARN", "✗", f"Plan rejected: {payload or 'no reason given'}")
    await r.delete(_approval_plan_key(task_id))
    return {
        "plan_approved": False,
        "replan_count": state.get("replan_count", 0) + 1,
        "human_interventions": interventions,
    }


async def get_pending_plan_async(task_id: str) -> dict | None:
    """Return the plan currently waiting for approval, or None."""
    raw = await _get_redis().get(_approval_plan_key(task_id))
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        logger.warning("Invalid pending approval plan for task %s", task_id)
        return None


async def _wait_for_decision(pubsub: redis.client.PubSub) -> tuple[Decision, dict | str | None]:
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        body = json.loads(message["data"])
        return body["decision"], body.get("payload")
    raise asyncio.TimeoutError


async def submit_decision_async(task_id: str, decision: Decision, payload: dict | str | None = None) -> None:
    r = _get_redis()
    await r.publish(_approval_channel(task_id), json.dumps({"decision": decision, "payload": payload}))


def add_dynamic_role(state: WorkflowState, role_name: str, role_config: dict) -> dict:
    dynamic_roles = [*state.get("dynamic_roles", []), {"role": role_name, "config": role_config}]
    logger.info("Dynamic role '%s' requested for task %s", role_name, state["task_id"])
    return {"dynamic_roles": dynamic_roles}


async def queue_dynamic_role_async(task_id: str, role_name: str, config: dict, reason: str | None) -> None:
    r = _get_redis()
    entry = json.dumps({"role": role_name, "config": config, "reason": reason})
    await r.rpush(_role_queue_key(task_id), entry)


async def drain_dynamic_roles(task_id: str) -> list[dict]:
    r = _get_redis()
    async with r.pipeline(transaction=True) as pipe:
        pipe.lrange(_role_queue_key(task_id), 0, -1)
        pipe.delete(_role_queue_key(task_id))
        raw_entries, _ = await pipe.execute()
    return [json.loads(entry) for entry in raw_entries]
