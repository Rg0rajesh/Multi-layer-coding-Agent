"""
Guardrail (C9) — screens each task and carries risk across a user's recent
workflow turns. A sequence of individually harmless prompts can therefore
raise the session risk instead of resetting to zero at every task.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from database import async_session_factory
from models.session_risk import SessionRiskScore
from models.task import Task
from services.llm_service import LLMGenerationError, classify_risk
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

DECAY_WEIGHT_CURRENT = 0.6
DECAY_WEIGHT_PRIOR = 0.4
BLOCK_THRESHOLD = 80
FLAG_THRESHOLD = 50
RISK_WINDOW_MINUTES = 30


async def guardrail_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "GUARDRAIL", "INIT", "◆", "Screening incoming task")

    prior_score = await _get_prior_score(task_id, state.get("user_id"))

    try:
        classification = await classify_risk(state["task_description"], prior_score=float(prior_score))
    except LLMGenerationError:
        logger.error("Guardrail classification failed for task %s — blocking", task_id)
        await emit_log(task_id, "GUARDRAIL", "ERROR", "✗", "Risk classifier unavailable — blocking as a precaution")
        await _save_score(task_id, float(prior_score), "block")
        return {"risk_score": float(prior_score), "risk_verdict": "block"}

    try:
        this_score = max(0.0, min(100.0, float(classification.get("risk_score", 100))))
    except (TypeError, ValueError):
        this_score = 100.0

    new_score = DECAY_WEIGHT_CURRENT * this_score + DECAY_WEIGHT_PRIOR * float(prior_score)
    verdict = _verdict_for(new_score)
    await _save_score(task_id, new_score, verdict)

    if verdict == "block":
        await emit_log(task_id, "GUARDRAIL", "ERROR", "✗", f"Task blocked — risk score {new_score:.0f}")
    elif verdict == "flag":
        await emit_log(task_id, "GUARDRAIL", "WARN", "▲", f"Flagged — risk score {new_score:.0f}, proceeding with caution")
    else:
        await emit_log(task_id, "GUARDRAIL", "PASS", "✓", f"Clear — risk score {new_score:.0f}")

    return {"risk_score": new_score, "risk_verdict": verdict}


def _verdict_for(score: float) -> str:
    if score > BLOCK_THRESHOLD:
        return "block"
    if score > FLAG_THRESHOLD:
        return "flag"
    return "allow"


async def _get_prior_score(task_id: str, user_id: str | None) -> Decimal:
    async with async_session_factory() as db:
        current = await db.get(Task, task_id)
        if current is None:
            return Decimal("0")

        # Carry the latest risk score from this user's recent tasks. The
        # user filter is essential: one user's adversarial sequence must
        # never affect another user's guardrail state.
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=RISK_WINDOW_MINUTES)
        stmt = (
            select(SessionRiskScore.running_score)
            .join(Task, Task.id == SessionRiskScore.task_id)
            .where(
                Task.user_id == (user_id or current.user_id),
                Task.id != current.id,
                Task.created_at >= cutoff,
            )
            .order_by(SessionRiskScore.updated_at.desc())
            .limit(1)
        )
        value = await db.scalar(stmt)
        if value is not None:
            return Decimal(str(value))

        own = await db.scalar(select(SessionRiskScore.running_score).where(SessionRiskScore.task_id == task_id))
        return Decimal(str(own)) if own is not None else Decimal("0")


async def _save_score(task_id: str, score: float, verdict: str) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(SessionRiskScore).where(SessionRiskScore.task_id == task_id))
        row = result.scalar_one_or_none()
        if row is None:
            db.add(SessionRiskScore(task_id=task_id, running_score=score, last_verdict=verdict))
        else:
            row.running_score = score
            row.last_verdict = verdict
        await db.commit()
