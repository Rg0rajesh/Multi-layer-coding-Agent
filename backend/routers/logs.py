# backend/routers/logs.py
"""
Backs the Dashboard log stream, Error Logs page, and Settings > alert rules.
Log entries are scoped through a task (and therefore through the task's
owner) — alert rules are scoped directly to the user, since they're not
tied to any one run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.log_entry import LogEntry
from models.user import User
from models.user_session import AlertRule
from services.auth_service import get_current_user
from services.task_service import TaskNotFoundError, get_task

router = APIRouter(tags=["logs"])


# ---------------------------------------------------------------- schemas

class LogEntryOut(BaseModel):
    id: int
    agent_name: str
    log_level: str
    prefix_icon: str | None
    message: str
    agent_color: str | None
    severity: str
    error_code: str | None
    is_resolved: bool
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LogListOut(BaseModel):
    items: list[LogEntryOut]
    total: int
    page: int
    page_size: int


class ResolveRequest(BaseModel):
    note: str | None = Field(None, max_length=500)


class LogAnalyticsOut(BaseModel):
    total: int
    unresolved: int
    by_severity: dict[str, int]
    by_agent: dict[str, int]


class AlertRuleCreate(BaseModel):
    name: str = Field(..., max_length=255)
    condition: dict
    action: dict
    is_active: bool = True


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    condition: dict | None = None
    action: dict | None = None
    is_active: bool | None = None

    def to_patch_dict(self) -> dict:
        return self.model_dump(exclude_unset=True)


class AlertRuleOut(BaseModel):
    id: UUID
    name: str
    condition: dict
    action: dict
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------- helpers

async def _get_owned_task(db: AsyncSession, task_id: UUID, user: User):
    try:
        return await get_task(db, task_id=task_id, user_id=user.id)
    except TaskNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")


async def _get_owned_alert_rule(db: AsyncSession, rule_id: UUID, user: User) -> AlertRule:
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user.id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert rule not found")
    return rule


# ----------------------------------------------------------------- routes
# Log entries

@router.get("/api/v1/tasks/{task_id}/logs", response_model=LogListOut)
async def list_logs(
    task_id: UUID,
    agent: str | None = None,
    severity: str | None = None,
    resolved: bool | None = None,
    search: str | None = None,
    since: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_task(db, task_id, current_user)

    conditions = [LogEntry.task_id == task_id]
    if agent:
        conditions.append(LogEntry.agent_name == agent.upper())
    if severity:
        conditions.append(LogEntry.severity == severity)
    if resolved is not None:
        conditions.append(LogEntry.is_resolved == resolved)
    if search:
        conditions.append(LogEntry.message.ilike(f"%{search}%"))
    if since:
        conditions.append(LogEntry.created_at >= since)

    # Same trick as task_service.list_tasks — total rides along with the
    # page via count().over() so filtering + counting is one round trip.
    stmt = (
        select(LogEntry, func.count().over().label("total_count"))
        .where(*conditions)
        .order_by(LogEntry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()

    if not rows:
        return LogListOut(items=[], total=0, page=page, page_size=page_size)

    return LogListOut(
        items=[row.LogEntry for row in rows],
        total=rows[0].total_count,
        page=page,
        page_size=page_size,
    )


@router.patch("/api/v1/tasks/{task_id}/logs/{log_id}/resolve", response_model=LogEntryOut)
async def resolve_log(
    task_id: UUID,
    log_id: int,
    body: ResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_task(db, task_id, current_user)

    result = await db.execute(
        select(LogEntry).where(LogEntry.id == log_id, LogEntry.task_id == task_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Log entry not found")

    entry.is_resolved = True
    # timezone-aware, matching every other timestamp column in the app —
    # datetime.utcnow() is naive and deprecated as of Python 3.12
    entry.resolved_at = datetime.now(timezone.utc)
    entry.resolved_by = current_user.id
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/api/v1/tasks/{task_id}/logs/analytics", response_model=LogAnalyticsOut)
async def get_log_analytics(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_task(db, task_id, current_user)

    # One GROUP BY covers both breakdowns instead of running a separate
    # query per bucket — O(distinct severity x agent) rows back, not O(n).
    breakdown = await db.execute(
        select(LogEntry.severity, LogEntry.agent_name, func.count().label("n"))
        .where(LogEntry.task_id == task_id)
        .group_by(LogEntry.severity, LogEntry.agent_name)
    )

    total = 0
    by_severity: dict[str, int] = {}
    by_agent: dict[str, int] = {}
    for severity, agent_name, count in breakdown:
        total += count
        by_severity[severity] = by_severity.get(severity, 0) + count
        by_agent[agent_name] = by_agent.get(agent_name, 0) + count

    unresolved = await db.scalar(
        select(func.count()).where(LogEntry.task_id == task_id, LogEntry.is_resolved.is_(False))
    )

    return LogAnalyticsOut(
        total=total, unresolved=unresolved or 0, by_severity=by_severity, by_agent=by_agent
    )


# ----------------------------------------------------------------- routes
# Alert rules — user-scoped, not tied to a single task

@router.get("/api/v1/alert-rules", response_model=list[AlertRuleOut])
async def list_alert_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AlertRule).where(AlertRule.user_id == current_user.id).order_by(AlertRule.created_at.desc())
    )
    return result.scalars().all()


@router.post("/api/v1/alert-rules", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    body: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = AlertRule(user_id=current_user.id, **body.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.patch("/api/v1/alert-rules/{rule_id}", response_model=AlertRuleOut)
async def update_alert_rule(
    rule_id: UUID,
    body: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = await _get_owned_alert_rule(db, rule_id, current_user)
    for field, value in body.to_patch_dict().items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/api/v1/alert-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = await _get_owned_alert_rule(db, rule_id, current_user)
    await db.delete(rule)
    await db.commit()