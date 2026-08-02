
# backend/routers/agents.py
"""
HTTP surface for the Human supervisor agent (C3). Everything here is a
thin wrapper over agents/human_agent.py — this file doesn't know how the
approval wait or the role queue actually work, just how to translate a
request into a call and a DB row.
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
from models.task import Task
from models.user import User
from services.auth_service import get_current_user
from services.log_service import emit_log
from services.task_service import TaskNotFoundError, get_task

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# Core pipeline agents — a human can add new roles, but can't shadow these.
RESERVED_AGENT_NAMES = {"PLANNER", "CODER", "TESTER", "REVIEWER", "SECURITY", "HUMAN", "SYSTEM"}


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


# ------------------------------------------------------------- helpers

async def _get_owned_task(db: AsyncSession, task_id: UUID, user: User) -> Task:
    try:
        return await get_task(db, task_id=task_id, user_id=user.id)
    except TaskNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")


# ----------------------------------------------------------------- routes

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