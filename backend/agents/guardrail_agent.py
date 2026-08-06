# backend/agents/guardrail_agent.py
"""
Guardrail (C9) — screens the incoming task before Planner ever sees it,
and keeps a running risk score across the session so a slow-building
jailbreak attempt doesn't reset to zero just because any single message
looks fine in isolation.

Runs first in the pipeline on purpose: Security (C2) scans code that's
already been generated, Guardrail is trying to catch the request before
that happens.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select

from database import async_session_factory
from models.session_risk import SessionRiskScore
from services.llm_service import LLMGenerationError, classify_risk
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

DECAY_WEIGHT_CURRENT = 0.6
DECAY_WEIGHT_PRIOR = 0.4
BLOCK_THRESHOLD = 80
FLAG_THRESHOLD = 50


async def guardrail_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "GUARDRAIL", "INIT", "◆", "Screening incoming task")

    prior_score = await _get_prior_score(task_id)

    try:
        classification = await classify_risk(state["task_description"], prior_score=float(prior_score))
    except LLMGenerationError:
        # Llama Guard down or returned garbage. Failing open here would
        # defeat the point of an adversarial-defense agent — block instead.
        logger.error("Guardrail classification failed for task %s — blocking", task_id)
        await emit_log(task_id, "GUARDRAIL", "ERROR", "✗", "Risk classifier unavailable — blocking as a precaution")
        await _save_score(task_id, float(prior_score), "block")
        return {"risk_score": float(prior_score), "risk_verdict": "block"}

    this_score = classification.get("risk_score", 0)
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


async def _get_prior_score(task_id: str) -> Decimal:
    async with async_session_factory() as db:
        result = await db.execute(select(SessionRiskScore).where(SessionRiskScore.task_id == task_id))
        row = result.scalar_one_or_none()
        return row.running_score if row else Decimal("0")


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