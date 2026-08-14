# backend/governance/opa_client.py
"""OPA-backed authorization for AGENTX execution."""
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
    """OPA did not return a usable authorization decision."""

async def opa_evaluate(policy_path: str, *, input_doc: dict) -> dict:
    try:
        response = await _get_client().post(f"/v1/data/{policy_path.replace('.', '/')}", json={"input": input_doc})
        response.raise_for_status()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise PolicyEvaluationError(f"OPA unreachable at {settings.opa_url}") from exc
    except httpx.HTTPStatusError as exc:
        raise PolicyEvaluationError(f"OPA returned {exc.response.status_code}") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise PolicyEvaluationError("OPA returned non-JSON data") from exc
    if "result" not in body or not isinstance(body["result"], dict):
        raise PolicyEvaluationError(f"No usable 'result' for {policy_path}")
    return body["result"]

async def opa_issue_token(task_id: str, needed_scope: dict) -> IdentityToken:
    decision = await opa_evaluate("agentx.authz", input_doc=needed_scope)
    allowed_scope = decision.get("allowed_scope")
    if not isinstance(allowed_scope, dict):
        raise PolicyEvaluationError("OPA returned no allowed_scope")
    allowed_tools = allowed_scope.get("tools", [])
    allowed_files = allowed_scope.get("files", [])
    requested_tools = set(needed_scope.get("requested_tools", []))
    requested_files = set(needed_scope.get("touched_files", []))
    if not isinstance(allowed_tools, list) or not isinstance(allowed_files, list):
        raise PolicyEvaluationError("OPA returned malformed scope")
    if not set(allowed_tools).issubset(requested_tools) or not set(allowed_files).issubset(requested_files):
        raise PolicyEvaluationError("OPA returned a scope outside the requested scope")
    token = IdentityToken(task_id=task_id, scope={"tools": allowed_tools, "files": allowed_files}, tool_call_log=[], expires_at=datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES))
    async with async_session_factory() as db:
        db.add(token)
        await db.commit()
        await db.refresh(token)
    return token

def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")

def resolve_scoped_file(target: str, allowed_files: list[str] | set[str]) -> str | None:
    target = _normalize_path(target)
    allowed = [_normalize_path(path) for path in allowed_files if isinstance(path, str)]
    if target in allowed:
        return target
    matches = [path for path in allowed if path.endswith(f"/{target}")]
    return matches[0] if len(matches) == 1 else None

async def log_tool_call(task_id: str, tool: str, *, target: str | None = None) -> bool:
    async with async_session_factory() as db:
        token = (await db.execute(select(IdentityToken).where(IdentityToken.task_id == task_id).order_by(IdentityToken.issued_at.desc()))).scalars().first()
        now = datetime.now(timezone.utc)
        if token is None:
            return False
        allowed_tools = set(token.scope.get("tools", []))
        allowed_files = set(token.scope.get("files", []))
        in_scope = token.expires_at is not None and token.expires_at > now and tool in allowed_tools
        resolved_target = target
        if tool in {"file_read", "file_write"}:
            resolved_target = resolve_scoped_file(target or "", allowed_files)
            in_scope = in_scope and resolved_target is not None
        token.tool_call_log = [*token.tool_call_log, {"tool": tool, "target": target, "resolved_target": resolved_target, "in_scope": in_scope, "at": now.isoformat()}]
        await db.commit()
        return in_scope

def derive_scope(plan: dict) -> dict:
    touched_files: list[str] = []
    for subtask in plan.get("subtasks", []):
        if isinstance(subtask, dict) and isinstance(subtask.get("file"), str) and subtask["file"].strip():
            touched_files.append(subtask["file"].strip())
    for key in ("files", "files_to_create", "files_to_modify", "touched_files"):
        values = plan.get(key, [])
        if isinstance(values, str): values = [values]
        if isinstance(values, list): touched_files.extend(v.strip() for v in values if isinstance(v, str) and v.strip())
    return {"requested_tools": ["file_read", "file_write", "pytest", "code_execute"], "touched_files": list(dict.fromkeys(touched_files)), "language": plan.get("language", "python")}
