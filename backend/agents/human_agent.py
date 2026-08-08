# backend/agents/human_agent.py
"""
Human agent (C3) — the human is a formal node, not just a viewer of the
final output. Three responsibilities:
  1. Pause the workflow at the plan-approval checkpoint until someone
     approves, edits, or rejects it.
  2. Let a person inject a brand-new agent role mid-workflow.
  3. Hand off both of the above to the API layer (routers/agents.py)
     without needing to know anything about HTTP.

State lives in Redis, not process memory. docker-compose.yml runs the
FastAPI app and the Celery worker as separate containers — an approval
submitted through the API and a workflow waiting on it are almost never
in the same process. Redis is the one thing both containers already
share (it's also the Celery broker and the WebSocket pub/sub backbone in
routers/websocket.py), so approvals and dynamic-role requests go through
it the same way.
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
Decision = Literal["approve", "reject", "edit"]

APPROVAL_CHANNEL_PREFIX = "agentx:approval:"
ROLE_QUEUE_KEY_PREFIX = "agentx:roles:"

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _approval_channel(task_id: str) -> str:
    return f"{APPROVAL_CHANNEL_PREFIX}{task_id}"


def _role_queue_key(task_id: str) -> str:
    return f"{ROLE_QUEUE_KEY_PREFIX}{task_id}"


# ---------------------------------------------------------------------------
# Plan approval
# ---------------------------------------------------------------------------

async def human_approval_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "HUMAN", "TASK", "→", "Waiting on plan approval")

    r = _get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(_approval_channel(task_id))

    try:
        decision, payload = await asyncio.wait_for(
            _wait_for_decision(pubsub), timeout=APPROVAL_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        await emit_log(task_id, "HUMAN", "ERROR", "✗", "No response within the approval window")
        return {"plan_approved": False}
    finally:
        await pubsub.unsubscribe(_approval_channel(task_id))
        await pubsub.aclose()

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


async def _wait_for_decision(pubsub: redis.client.PubSub) -> tuple[Decision, dict | str | None]:
    """Blocks on the subscription until submit_decision_async() publishes
    something. Returns as soon as one real message arrives — subscribe/
    unsubscribe confirmations come through as different message types and
    are skipped."""
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        body = json.loads(message["data"])
        return body["decision"], body.get("payload")

    raise asyncio.TimeoutError  # pragma: no cover — listen() shouldn't exit on its own


async def submit_decision_async(task_id: str, decision: Decision, payload: dict | str | None = None) -> None:
    """
    Called from the API layer (routers/agents.py), which already runs
    inside an event loop — this publishes directly rather than spinning
    one up. Fire-and-forget: if nobody's subscribed (task already timed
    out, or never reached the approval node), the message is just dropped,
    same end result as the old in-memory version returning False.
    """
    r = _get_redis()
    await r.publish(_approval_channel(task_id), json.dumps({"decision": decision, "payload": payload}))


# ---------------------------------------------------------------------------
# Dynamic role assignment
# ---------------------------------------------------------------------------

def add_dynamic_role(state: WorkflowState, role_name: str, role_config: dict) -> dict:
    """Applies a role addition directly to workflow state. Used by the
    orchestrator once it's drained the queue below, when it's already
    holding a live WorkflowState to fold the addition into."""
    dynamic_roles = [*state.get("dynamic_roles", []), {"role": role_name, "config": role_config}]
    logger.info("Dynamic role '%s' requested for task %s", role_name, state["task_id"])
    return {"dynamic_roles": dynamic_roles}


async def queue_dynamic_role_async(task_id: str, role_name: str, config: dict, reason: str | None) -> None:
    """Called from the API layer when a human asks for a new agent
    mid-run. The router doesn't have a live WorkflowState to hand this
    to directly, so it goes on a Redis list until the orchestrator's
    next node transition picks it up."""
    r = _get_redis()
    entry = json.dumps({"role": role_name, "config": config, "reason": reason})
    await r.rpush(_role_queue_key(task_id), entry)


async def drain_dynamic_roles(task_id: str) -> list[dict]:
    """Orchestrator calls this between nodes to pick up anything queued
    since the last check. lrange + delete inside a pipeline so the read
    and the clear happen atomically — two concurrent drains can't each
    walk away with half the list."""
    r = _get_redis()
    async with r.pipeline(transaction=True) as pipe:
        pipe.lrange(_role_queue_key(task_id), 0, -1)
        pipe.delete(_role_queue_key(task_id))
        raw_entries, _ = await pipe.execute()

    return [json.loads(entry) for entry in raw_entries]