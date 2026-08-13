"""Authenticated evaluation/metrics endpoints for research experiments."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from evaluation.metrics import compute_task_metrics
from models.user import User
from services.auth_service import get_current_user
from services.task_service import TaskNotFoundError, get_task

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])


@router.get("/tasks/{task_id}/metrics")
async def task_metrics(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await get_task(db, task_id=task_id, user_id=current_user.id)
    except TaskNotFoundError:
        raise HTTPException(404, "Task not found")

    metrics = await compute_task_metrics(db, task_id=task_id)
    return {"task_id": str(task_id), **metrics.as_dict()}
