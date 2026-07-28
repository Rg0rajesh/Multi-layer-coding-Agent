# backend/services/log_service.py
"""
Every agent writes through here instead of touching the DB or the WS
connection manager directly — one place to change if the log format or
transport ever changes.
"""
from __future__ import annotations

import logging

from database import async_session_factory
from models.log_entry import LogEntry

logger = logging.getLogger(__name__)

AGENT_COLORS = {
    "PLANNER": "#E8FF47",
    "CODER": "#00C896",
    "TESTER": "#FF6B35",
    "REVIEWER": "#FF3C3C",
    "SECURITY": "#FF3C3C",
    "HUMAN": "#FFFFFF",
    "SYSTEM": "#888888",
}


async def emit_log(task_id: str, agent_name: str, level: str, icon: str, message: str) -> None:
    async with async_session_factory() as db:
        db.add(LogEntry(
            task_id=task_id,
            agent_name=agent_name,
            log_level=level,
            prefix_icon=icon,
            message=message,
            agent_color=AGENT_COLORS.get(agent_name),
            severity="critical" if level == "ERROR" else "info",
        ))
        await db.commit()

    try:
        # Deferred import — routers/websocket.py doesn't exist yet (Step 9).
        # Once it does, this fans the same line out over the live socket.
        from routers.websocket import publish_log
        await publish_log(task_id, agent_name, level, icon, message)
    except ImportError:
        pass