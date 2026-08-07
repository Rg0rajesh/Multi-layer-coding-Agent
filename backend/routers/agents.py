# backend/routers/agents.py
"""
HTTP surface for the Human supervisor agent (C3) plus the read-only
governance/memory endpoints (C6/C7/C8/C9) documented in Master Prompt
Part 3. Everything here is a thin wrapper over the agent modules and their
tables — this file doesn't know how approval waits, OPA, or curation
actually work, just how to translate a request into a call and a DB row.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents import human_agent
from database import get_db
from models.agent_run import AgentRun
from models.curated_memory import CuratedMemory
from models.identity_token import IdentityToken
from models.session_risk import SessionRiskScore
from models.task import Task
from models.user import User
from services.auth_service import get_current_user
from services.log_service import emit_log
from services.task_service import TaskNotFoundError, get_task

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# Core pipeline agents — a human can add new roles, but can't shadow these.
RESERVED_AGENT_NAMES = {
    "GUARDRAIL", "PLANNER", "GROUNDING", "HUMAN", "IDENTITY_BROKER",
    "CODER", "TESTER", "SECURITY", "REVIEWER", "CONTEXT_CURATOR", "SYSTEM",
}


# ---------------------------------------------------------------- schemas

class AgentRunOut(BaseModel):
    id: UUID
    agent_name: str
    agent_color: str | None
    status: str
    current_subtask: str | None
    step_current: int
    step_total: int
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None

    model_config = {"from_attributes": True}


class RejectRequest(BaseModel):
    reason: str | None = Field(None, max_length=1000)


class EditPlanRequest(BaseModel):
    plan: dict


class AddRoleRequest(BaseModel):
    role_name: str = Field(..., min_length=2, max_length=50)
    reason: str | None = Field(None, max_length=1000)
    config: dict = Field(default_factory=dict)


class RiskScoreOut(BaseModel):
    running_score: float
    last_verdict: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class GroundingReportOut(BaseModel):
    grounded: bool
    unsupported_claims: list


class IdentityTokenOut(BaseModel):
    id: UUID
    scope: dict
    tool_call_log: list
    issued_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class CuratedMemoryOut(BaseModel):
    id: UUID
    tag: str
    summary: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------- helpers

async def _get_owned_task(db: AsyncSession, task_id: UUID, user: User) -> Task:
    try:
        return await get_task(db, task_id=task_id, user_id=user.id)
    except TaskNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")


# ----------------------------------------------------------------- routes
# Human supervisor (C3)

@router.get("/runs/{task_id}", response_model=list[AgentRunOut])
async def list_agent_runs(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_task(db, task_id, current_user)

    result = await db.execute(
        select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.started_at)
    )
    return result.scalars().all()


@router.post("/{task_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve_plan(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_task(db, task_id, current_user)

    if not human_agent.submit_decision(str(task_id), "approve"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting on approval for this task")


@router.post("/{task_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_plan(
    task_id: UUID,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_task(db, task_id, current_user)

    if not human_agent.submit_decision(str(task_id), "reject", body.reason):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting on approval for this task")


@router.post("/{task_id}/edit-plan", status_code=status.HTTP_204_NO_CONTENT)
async def edit_plan(
    task_id: UUID,
    body: EditPlanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_task(db, task_id, current_user)

    if not human_agent.submit_decision(str(task_id), "edit", body.plan):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is waiting on approval for this task")


@router.post("/{task_id}/add-role", response_model=AgentRunOut, status_code=status.HTTP_201_CREATED)
async def add_dynamic_role(
    task_id: UUID,
    body: AddRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    The C3 novelty: a human adding a brand-new agent to a workflow that's
    already running, not just approving what's already there. Writes an
    audit row immediately (so it shows up in Live Monitor and survives a
    page refresh) and queues the request for the workflow to pick up on
    its next node transition.
    """
    await _get_owned_task(db, task_id, current_user)

    role_name = body.role_name.strip().upper()
    if role_name in RESERVED_AGENT_NAMES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"'{role_name}' is a core pipeline agent — pick a different name for the new role",
        )

    agent_run = AgentRun(
        task_id=task_id,
        agent_name=role_name,
        status="queued",
        input_data=body.config,
        stats={"requested_by": str(current_user.id), "reason": body.reason},
    )
    db.add(agent_run)

    task = await db.get(Task, task_id)
    task.human_interventions += 1

    await db.commit()
    await db.refresh(agent_run)

    # Only after the DB write succeeds — no point queuing a role the audit
    # trail doesn't know about.
    human_agent.queue_dynamic_role(str(task_id), role_name, body.config, body.reason)

    await emit_log(
        str(task_id), "HUMAN", "TASK", "✎",
        f"Dynamic role requested: {role_name}" + (f" — {body.reason}" if body.reason else ""),
    )

    return agent_run


# ----------------------------------------------------------------- routes
# Governance + memory read endpoints (C6/C7/C8/C9)

@router.get("/{task_id}/risk-score", response_model=RiskScoreOut)
async def get_risk_score(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Guardrail's current running score for this task's session."""
    await _get_owned_task(db, task_id, current_user)

    row = (
        await db.execute(select(SessionRiskScore).where(SessionRiskScore.task_id == task_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guardrail hasn't scored this task yet")
    return row


@router.get("/{task_id}/grounding-report", response_model=GroundingReportOut)
async def get_grounding_report(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grounding's pass/fail verdict plus any unsupported claims found in
    the plan. Read from agent_runs.output_data — Grounding is deterministic
    and writes there once per run."""
    await _get_owned_task(db, task_id, current_user)

    run = (
        await db.execute(
            select(AgentRun)
            .where(AgentRun.task_id == task_id, AgentRun.agent_name == "GROUNDING")
            .order_by(AgentRun.completed_at.desc().nullslast())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None or not run.output_data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No grounding report for this task yet")
    return run.output_data


@router.get("/{task_id}/identity-token", response_model=IdentityTokenOut)
async def get_identity_token(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Scope + expiry + tool_call_log only — never returns raw secrets,
    there aren't any to return: the token itself never leaves this table."""
    await _get_owned_task(db, task_id, current_user)

    token = (
        await db.execute(
            select(IdentityToken)
            .where(IdentityToken.task_id == task_id)
            .order_by(IdentityToken.issued_at.desc())
        )
    ).scalars().first()
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No credential issued for this task yet")
    return token


@router.get("/{task_id}/curated-memory", response_model=list[CuratedMemoryOut])
async def get_curated_memory(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Items this specific task run promoted into long-term project
    memory. Standalone tasks with no project have nothing to promote to,
    so this returns an empty list rather than a 404 for those."""
    task = await _get_owned_task(db, task_id, current_user)
    if task.project_id is None:
        return []

    result = await db.execute(select(CuratedMemory).where(CuratedMemory.source_task_id == task_id))
    return result.scalars().all()