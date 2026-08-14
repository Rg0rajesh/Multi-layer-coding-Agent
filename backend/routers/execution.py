from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from services.auth_service import get_current_user
from services.code_execution import CodeExecutionError, execute_code, list_runtimes
from services.task_service import TaskNotFoundError, get_task

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])

class RunRequest(BaseModel):
    language: str = Field(..., min_length=1, max_length=50)
    code: str = Field(..., min_length=1, max_length=200_000)
    stdin: str = Field("", max_length=20_000)
    filename: str | None = Field(None, max_length=255)
    extra_files: list[dict[str, str]] = Field(default_factory=list)

class TaskRunRequest(RunRequest):
    task_id: str

@router.get("/runtimes")
async def runtimes(current_user: User = Depends(get_current_user)):
    try:
        return {"runtimes": await list_runtimes()}
    except CodeExecutionError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

@router.post("/run")
async def run_code(payload: RunRequest, current_user: User = Depends(get_current_user)):
    try:
        return await execute_code(language=payload.language, code=payload.code, stdin=payload.stdin, filename=payload.filename, extra_files=payload.extra_files)
    except CodeExecutionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

@router.post("/task")
async def run_task_code(payload: TaskRunRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        await get_task(db, task_id=payload.task_id, user_id=current_user.id)
    except TaskNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    try:
        return await execute_code(language=payload.language, code=payload.code, stdin=payload.stdin, filename=payload.filename, extra_files=payload.extra_files)
    except CodeExecutionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
