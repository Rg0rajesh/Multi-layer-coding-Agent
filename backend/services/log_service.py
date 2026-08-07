# backend/services/log_service.py
"""
Every agent writes through here instead of touching the DB, the alert
system, or the WS connection manager directly — one place to change if
the log format, alerting rules, or transport ever change.
"""
from __future__ import annotations

import logging

from database import async_session_factory
from models.log_entry import LogEntry
from services.notification import check_alert_rules

logger = logging.getLogger(__name__)

AGENT_COLORS = {
    "PLANNER": "#E8FF47",
    "CODER": "#00C896",
    "TESTER": "#FF6B35",
    "REVIEWER": "#FF3C3C",
    "SECURITY": "#FF3C3C",
    "HUMAN": "#FFFFFF",
    "SYSTEM": "#888888",
    # v2 — Governance + memory-curation agents (Master Prompt v2.1 Part 6)
    "GUARDRAIL": "#FF3C3C",        # blocking / adversarial-defense — same red as Security
    "IDENTITY_BROKER": "#E8FF47",  # governance checkpoint — lime, same family as Planner
    "GROUNDING": "#00C896",        # verification step — same family as Coder/Tester
    "CONTEXT_CURATOR": "#888888",  # passive/background — neutral like System
}


async def emit_log(
    task_id: str,
    agent_name: str,
    level: str,
    icon: str,
    message: str,
    user_id: str | None = None,
) -> None:
    """
    user_id is optional and only used to scope alert-rule matching — most
    call sites don't have it handy (or don't need alerts firing on that
    particular line) and that's fine, this still logs and streams either way.
    """
    severity = "critical" if level == "ERROR" else "info"

    async with async_session_factory() as db:
        db.add(LogEntry(
            task_id=task_id,
            agent_name=agent_name,
            log_level=level,
            prefix_icon=icon,
            message=message,
            agent_color=AGENT_COLORS.get(agent_name),
            severity=severity,
        ))
        await db.commit()

        if user_id:
            try:
                await check_alert_rules(db, {
                    "task_id": task_id,
                    "agent_name": agent_name,
                    "log_level": level,
                    "message": message,
                    "severity": severity,
                    "user_id": user_id,
                })
            except Exception:
                # An alert-rule hiccup (bad webhook, SendGrid down) is never
                # worth failing the agent step that triggered this log line.
                logger.warning("Alert rule check failed for task %s", task_id, exc_info=True)

    try:
        # Deferred import — routers/websocket.py doesn't exist at import
        # time in every context this module gets loaded in (e.g. Celery
        # workers before the API app has started). Once it's up, this fans
        # the same line out over the live socket.
        from routers.websocket import publish_log
        await publish_log(task_id, agent_name, level, icon, message)
    except ImportError:
        pass