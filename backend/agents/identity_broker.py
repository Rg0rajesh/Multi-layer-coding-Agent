# backend/agents/identity_broker.py
"""
Identity Broker (C7) — issues a short-lived, scoped credential once Human
has approved the plan, so Coder/Tester run under "what this task actually
needs" instead of the developer's full account permissions.

Deterministic, same reasoning as Grounding — the scope decision belongs to
OPA (governance/policies/workspace_policy.rego), not an LLM call.
"""
from __future__ import annotations

import logging

from governance.opa_client import PolicyEvaluationError, derive_scope, opa_issue_token
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)


async def identity_broker_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "IDENTITY_BROKER", "TASK", "→", "Issuing scoped credential")

    needed_scope = derive_scope(state.get("plan", {}))

    try:
        token = await opa_issue_token(task_id, needed_scope)
    except PolicyEvaluationError as exc:
        logger.error("Identity Broker couldn't reach OPA for task %s: %s", task_id, exc)
        await emit_log(task_id, "IDENTITY_BROKER", "ERROR", "✗", "Policy engine unreachable — no credential issued")
        return {"identity_token": None}

    granted_tools = token.scope.get("tools", [])
    await emit_log(
        task_id, "IDENTITY_BROKER", "PASS", "✓",
        f"Credential issued — {len(granted_tools)} tool(s) granted, expires {token.expires_at:%H:%M UTC}",
    )

    return {
        "identity_token": {
            "id": str(token.id),
            "scope": token.scope,
            "expires_at": token.expires_at.isoformat(),
        }
    }