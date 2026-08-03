
# backend/routers/outputs.py
"""
Code Output page's backend: file tree, single-file content, and a ZIP
download. All ownership checks route through task_service.get_task so a
task_id you don't own 404s the same way everywhere else in the API does.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from services.auth_service import get_current_user
from services.output_service import (
    OutputNotFoundError,
    build_file_tree,
    build_zip,
    get_output,
    list_outputs,
)
from services.task_service import TaskNotFoundError, get_task

router = APIRouter(prefix="/api/v1/tasks/{task_id}/outputs", tags=["outputs"])


# ---------------------------------------------------------------- schemas

class CodeOutputSummary(BaseModel):
    id: UUID
    file_path: str
    file_name: str
    file_type: str | None
    language: str | None
    line_count: int
    is_new_file: bool
    is_test_file: bool
    is_doc_file: bool

    model_config = {"from_attributes": True}


class CodeOutputDetail(CodeOutputSummary):
    content: str
    annotations: list


# ------------------------------------------------------------- helpers

async def _get_owned_task(db: AsyncSession, task_id: UUID, user: User):
    try:
        return await get_task(db, task_id=task_id, user_id=user.id)
    except TaskNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")


# ----------------------------------------------------------------- routes

@router.get("", response_model=list[CodeOutputSummary])
async def list_files(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Flat list — used by anything that just needs metadata, not the tree."""
    await _get_owned_task(db, task_id, current_user)
    return await list_outputs(db, task_id=task_id)


@router.get("/tree")
async def get_file_tree(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_task(db, task_id, current_user)
    outputs = await list_outputs(db, task_id=task_id)
    return build_file_tree(outputs)


@router.get("/{output_id}", response_model=CodeOutputDetail)
async def get_file(
    task_id: UUID,
    output_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_owned_task(db, task_id, current_user)
    try:
        return await get_output(db, task_id=task_id, output_id=output_id)
    except OutputNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")


@router.get("/download/zip")
async def download_zip(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await _get_owned_task(db, task_id, current_user)
    outputs = await list_outputs(db, task_id=task_id)

    if not outputs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This task has no generated files yet")

    archive = build_zip(outputs)
    filename = f"{task.title[:50].strip().replace(' ', '_') or 'agentx-output'}.zip"

    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )