# backend/governance/opa_client.py
"""
Talks to Open Policy Agent for scoped-permission decisions and turns the
result into an IdentityToken row. Identity Broker is the only caller —
see agents/identity_broker.py.

OPA does the actual authorization math in Rego, not Python, on purpose:
we don't want a probabilistic model anywhere near "can this task touch
the filesystem."
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from config import settings
from database import async_session_factory
from models.identity_token import IdentityToken

logger = logging.getLogger(__name__)

TOKEN_TTL_MINUTES = 15
OPA_TIMEOUT_SECONDS = 5

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=settings.opa_url, timeout=OPA_TIMEOUT_SECONDS)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


class PolicyEvaluationError(Exception):
    """OPA didn't return a usable decision — unreachable, bad policy path,
    or a malformed response. Treat this as "deny everything," not as
    something worth retrying with a wider scope."""


async def opa_evaluate(policy_path: str, *, input_doc: dict) -> dict:
    """policy_path is dot-separated, e.g. 'agentx.authz.scope' — gets
    translated into OPA's /v1/data/<path> URL shape."""
    url = f"/v1/data/{policy_path.replace('.', '/')}"

    try:
        response = await _get_client().post(url, json={"input": input_doc})
        response.raise_for_status()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise PolicyEvaluationError(f"OPA unreachable at {settings.opa_url}") from exc
    except httpx.HTTPStatusError as exc:
        raise PolicyEvaluationError(f"OPA returned {exc.response.status_code}") from exc

    body = response.json()
    if "result" not in body:
        raise PolicyEvaluationError(f"No 'result' key in OPA response for {policy_path}")
    return body["result"]


async def opa_issue_token(task_id: str, needed_scope: dict) -> IdentityToken:
    """Evaluates the workspace policy against what this run says it needs,
    then persists a token scoped to whatever OPA actually granted — which
    may be narrower than needed_scope if the policy trims it."""
    decision = await opa_evaluate("agentx.authz.scope", input_doc=needed_scope)
    allowed_scope = decision.get("allowed_scope", {})

    if not allowed_scope.get("tools"):
        logger.warning("OPA granted an empty tool scope for task %s — Coder/Tester will have nothing to work with", task_id)

    token = IdentityToken(
        task_id=task_id,
        scope=allowed_scope,
        tool_call_log=[],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES),
    )

    async with async_session_factory() as db:
        db.add(token)
        await db.commit()
        await db.refresh(token)

    return token


async def log_tool_call(task_id: str, tool: str, *, target: str | None = None) -> bool:
    """
    Appends one entry to the task's active token's tool_call_log — this is
    what Coder/Tester are supposed to call every time they actually do
    something under the credential Identity Broker issued them.

    Without this, tool_call_log stays permanently empty and
    evaluation.metrics._scope_violations() has nothing to count, which
    means the C7 metric always reports zero regardless of what actually
    happened. Returns whether the call was in-scope, so callers can decide
    whether to act on it or just log the attempt.

    A missing token (OPA was unreachable, or this ran before Identity
    Broker existed in an older task) isn't fatal here — nothing to log
    against, so we just say "allowed" and let the caller proceed. Identity
    Broker already fails loudly on its own if OPA is down; this function's
    job is bookkeeping, not re-litigating that decision.
    """
    async with async_session_factory() as db:
        token = (
            await db.execute(
                select(IdentityToken)
                .where(IdentityToken.task_id == task_id)
                .order_by(IdentityToken.issued_at.desc())
            )
        ).scalars().first()

        if token is None:
            return True

        allowed_tools = set(token.scope.get("tools", []))
        in_scope = tool in allowed_tools

        token.tool_call_log = [
            *token.tool_call_log,
            {
                "tool": tool,
                "target": target,
                "in_scope": in_scope,
                "at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        await db.commit()

        if not in_scope:
            logger.warning(
                "Tool call outside granted scope — task %s tried %r (target=%r), token only grants %s",
                task_id, tool, target, sorted(allowed_tools),
            )

        return in_scope


def derive_scope(plan: dict) -> dict:
    """Turns a Planner subtask list into the input shape the Rego policy
    expects. Tester always runs in the pipeline regardless of what the
    plan says, so pytest is always requested — no need to inspect the
    subtasks for that."""
    subtasks = plan.get("subtasks", [])
    touched_files = [st["file"] for st in subtasks if st.get("file")]

    return {
        "requested_tools": ["file_read", "file_write", "pytest"],
        "touched_files": touched_files,
        "language": plan.get("language", "python"),
    }