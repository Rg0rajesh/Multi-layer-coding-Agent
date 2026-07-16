#backend/routers/tasks.py
"""Task CRUD + listing. Auth, execution triggers, and agent wiring live
elsewhere — this router is deliberately just the REST surface over
services/task_service.py.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from services.auth_service import get_current_user
from services.task_service import (
    Page,
    TaskFilters,
    TaskNotFoundError,
    create_task,
    delete_task,
    get_task,
    list_tasks,
    update_task,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


# ---------------------------------------------------------------- schemas

class TaskCreate(BaseModel):
    title: str = Field(..., max_length=500)
    description: str | None = None
    language: str | None = None
    framework: str | None = None
    project_type: str | None = None
    project_id: UUID | None = None
    priority: str = "medium"
    coordination_pattern: str = "sequential"
    max_exec_minutes: int = Field(10, ge=1, le=120)
    output_format: str = "commented"
    git_integration: bool = False
    agents_config: dict = Field(default_factory=dict)
    context_files: list = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: str | None = Field(None, max_length=500)
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    agents_config: dict | None = None
    context_files: list | None = None

    def to_patch_dict(self) -> dict:
        # Only fields the client actually sent — PATCH semantics, not PUT.
        return self.model_dump(exclude_unset=True)


class TaskOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    language: str | None
    framework: str | None
    status: str
    priority: str
    coordination_pattern: str
    replan_count: int
    coder_retries: int
    safety_issues_found: int
    human_interventions: int
    review_score: float | None

    model_config = {"from_attributes": True}


class TaskListOut(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def from_page(cls, page: Page) -> "TaskListOut":
        return cls(
            items=page.items,
            total=page.total,
            page=page.page,
            page_size=page.page_size,
            total_pages=page.total_pages,
        )


# ----------------------------------------------------------------- routes

@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task_endpoint(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await create_task(db, user_id=current_user.id, data=payload.model_dump())


@router.get("", response_model=TaskListOut)
async def list_tasks_endpoint(
    status_: str | None = Query(None, alias="status"),
    priority: str | None = None,
    language: str | None = None,
    project_id: UUID | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = "created_at",
    sort_desc: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filters = TaskFilters(
        status=status_,
        priority=priority,
        language=language,
        project_id=project_id,
        search=search,
    )
    page_result = await list_tasks(
        db,
        user_id=current_user.id,
        filters=filters,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_desc=sort_desc,
    )
    return TaskListOut.from_page(page_result)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task_endpoint(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await get_task(db, task_id=task_id, user_id=current_user.id)
    except TaskNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task_endpoint(
    task_id: UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await update_task(
            db, task_id=task_id, user_id=current_user.id, data=payload.to_patch_dict()
        )
    except TaskNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_endpoint(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        await delete_task(db, task_id=task_id, user_id=current_user.id)
    except TaskNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")