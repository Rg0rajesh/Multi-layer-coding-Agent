#backend/services/task_service.py
"""
Task CRUD + listing. Deliberately HTTP-agnostic — this file only knows
about SQLAlchemy, not FastAPI. Routers translate TaskNotFoundError into
a 404; that keeps this layer testable (and reusable from Celery) without
spinning up the API.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.task import Task


class TaskNotFoundError(Exception):
    """Task doesn't exist, or doesn't belong to the requesting user."""

    def __init__(self, task_id: UUID):
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")


# Whitelisted so a bad query param can't turn into getattr() on something
# that isn't a column.
ALLOWED_SORT_FIELDS = {"created_at", "updated_at", "priority", "status", "title"}


@dataclass
class TaskFilters:
    status: str | None = None
    priority: str | None = None
    language: str | None = None
    project_id: UUID | None = None
    search: str | None = None


@dataclass
class Page:
    items: list[Task]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.page_size) if self.page_size else 0


async def create_task(db: AsyncSession, *, user_id: UUID, data: dict) -> Task:
    task = Task(user_id=user_id, **data)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, *, task_id: UUID, user_id: UUID) -> Task:
    row = await db.execute(
        select(Task).where(Task.id == task_id, Task.user_id == user_id)
    )
    task = row.scalar_one_or_none()
    if task is None:
        raise TaskNotFoundError(task_id)
    return task


async def list_tasks(
    db: AsyncSession,
    *,
    user_id: UUID,
    filters: TaskFilters,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_desc: bool = True,
) -> Page:
    sort_col = getattr(Task, sort_by if sort_by in ALLOWED_SORT_FIELDS else "created_at")

    conditions = [Task.user_id == user_id]
    if filters.status:
        conditions.append(Task.status == filters.status)
    if filters.priority:
        conditions.append(Task.priority == filters.priority)
    if filters.language:
        conditions.append(Task.language == filters.language)
    if filters.project_id:
        conditions.append(Task.project_id == filters.project_id)
    if filters.search:
        conditions.append(Task.title.ilike(f"%{filters.search}%"))

    # One round trip instead of two: func.count().over() rides along with
    # the page of rows, so we get the filtered total without a second
    # COUNT(*) query. Every row carries the same total_count value; we
    # just read it off the first one.
    stmt = (
        select(Task, func.count().over().label("total_count"))
        .where(*conditions)
        .order_by(sort_col.desc() if sort_desc else sort_col.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).all()

    if not rows:
        return Page(items=[], total=0, page=page, page_size=page_size)

    return Page(
        items=[row.Task for row in rows],
        total=rows[0].total_count,
        page=page,
        page_size=page_size,
    )


async def update_task(db: AsyncSession, *, task_id: UUID, user_id: UUID, data: dict) -> Task:
    task = await get_task(db, task_id=task_id, user_id=user_id)
    for field, value in data.items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, *, task_id: UUID, user_id: UUID) -> None:
    task = await get_task(db, task_id=task_id, user_id=user_id)
    await db.delete(task)
    await db.commit()