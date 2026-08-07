
# backend/services/notification.py
"""
Fires alert_rules against incoming log entries. log_service.emit_log calls
check_alert_rules() after it writes each log line — this module doesn't
poll anything, it just reacts to whatever's already flowing through.

Two channels for now: email (SendGrid) and Slack (incoming webhook). Both
are optional — if the relevant setting isn't configured, that channel is
skipped with a warning instead of throwing.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.user_session import AlertRule

logger = logging.getLogger(__name__)

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
REQUEST_TIMEOUT_SECONDS = 10

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---------------------------------------------------------------------------
# Rule matching
# ---------------------------------------------------------------------------

async def check_alert_rules(db: AsyncSession, log_entry: dict[str, Any]) -> None:
    """
    log_entry is the same shape log_service builds before writing a
    LogEntry row: {task_id, agent_name, log_level, message, severity,
    error_code, user_id}. user_id is required here — alert_rules are
    scoped per user, not per task.
    """
    user_id = log_entry.get("user_id")
    if user_id is None:
        return  # nothing to scope the rule lookup to

    result = await db.execute(
        select(AlertRule).where(AlertRule.user_id == user_id, AlertRule.is_active.is_(True))
    )
    rules = result.scalars().all()
    if not rules:
        return

    for rule in rules:
        if _matches(rule.condition, log_entry):
            await _dispatch(rule.action, log_entry)


def _matches(condition: dict[str, Any], log_entry: dict[str, Any]) -> bool:
    """condition is a flat dict of field -> expected value, e.g.
    {"severity": "critical"} or {"severity": "critical", "agent_name": "SECURITY"}.
    Every key in condition has to match — no OR logic, no wildcards. If you
    need more than that, it's worth a rules engine; nothing here needs one yet."""
    return all(log_entry.get(field) == expected for field, expected in condition.items())


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def _dispatch(action: dict[str, Any], log_entry: dict[str, Any]) -> None:
    action_type = action.get("type")

    if action_type == "email":
        await send_email(
            to=action.get("to", ""),
            subject=f"AGENTX alert — {log_entry.get('agent_name')} {log_entry.get('severity')}",
            body=log_entry.get("message", ""),
        )
    elif action_type == "slack":
        await send_slack(_format_slack_message(log_entry), webhook_url=action.get("webhook_url"))
    else:
        logger.warning("Alert rule has an unrecognised action type: %r", action_type)


def _format_slack_message(log_entry: dict[str, Any]) -> str:
    agent = log_entry.get("agent_name", "UNKNOWN")
    severity = log_entry.get("severity", "info")
    message = log_entry.get("message", "")
    return f"*[{severity.upper()}]* `{agent}` — {message}"


# ---------------------------------------------------------------------------
# Email — SendGrid
# ---------------------------------------------------------------------------

async def send_email(*, to: str, subject: str, body: str) -> bool:
    if not settings.sendgrid_api_key:
        logger.warning("SENDGRID_API_KEY not set — skipping email alert to %s", to)
        return False
    if not to:
        logger.warning("Alert rule action had no 'to' address — skipping")
        return False

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": "alerts@agentx.dev"},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    headers = {"Authorization": f"Bearer {settings.sendgrid_api_key}"}

    try:
        response = await _get_client().post(SENDGRID_URL, json=payload, headers=headers)
        response.raise_for_status()
        return True
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
        logger.warning("Failed to send alert email to %s: %s", to, exc)
        return False


# ---------------------------------------------------------------------------
# Slack — incoming webhook
# ---------------------------------------------------------------------------

async def send_slack(message: str, *, webhook_url: str | None = None) -> bool:
    url = webhook_url or settings.slack_webhook_url
    if not url:
        logger.warning("No Slack webhook configured — skipping alert")
        return False

    try:
        response = await _get_client().post(url, json={"text": message})
        response.raise_for_status()
        return True
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
        logger.warning("Failed to post Slack alert: %s", exc)
        return False