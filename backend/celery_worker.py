# backend/celery_worker.py
"""
Celery entrypoint for AGENTX's background task execution.

This file owns exactly one job: take a task_id off the queue, run the
agent workflow against it, and make sure the DB reflects what happened.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from celery import Celery
from celery.signals import worker_process_init
from celery.exceptions import SoftTimeLimitExceeded

from config import settings
from database import async_session_factory, engine
from models.task import Task
from models.log_entry import LogEntry
from services.llm_service import OllamaUnavailableError

logger = logging.getLogger(__name__)

celery_app = Celery(
    "agentx",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Ollama-based multi-agent workflows can legitimately take several minutes.
# Keep a generous default so slow local model generation is not killed early.
DEFAULT_SOFT_LIMIT_SECONDS = 20 * 60
DEFAULT_HARD_LIMIT_SECONDS = 25 * 60

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=50,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=DEFAULT_SOFT_LIMIT_SECONDS,
    task_time_limit=DEFAULT_HARD_LIMIT_SECONDS,
)


class GovernanceUnavailableError(Exception):
    """Raised when OPA cannot be reached during credential issuance."""


_worker_loop: asyncio.AbstractEventLoop | None = None


@worker_process_init.connect
def _init_worker_process(**_kwargs) -> None:
    global _worker_loop
    _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    _worker_loop.run_until_complete(engine.dispose())
    logger.info("Worker process initialized, connection pool reset post-fork")


def _run_async(coro):
    loop = _worker_loop or asyncio.get_event_loop()
    return loop.run_until_complete(coro)


async def _mark_task_started(task_id: str) -> None:
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await db.commit()


async def _mark_task_finished(task_id: str, *, success: bool, error: str | None = None) -> None:
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return

        now = datetime.now(timezone.utc)
        task.status = "completed" if success else "failed"
        task.completed_at = now
        if task.started_at:
            task.elapsed_seconds = int((now - task.started_at).total_seconds())

        if not success and error:
            db.add(LogEntry(
                task_id=task.id,
                agent_name="SYSTEM",
                log_level="ERROR",
                message=error[:2000],
                severity="critical",
            ))

        await db.commit()


@celery_app.task(
    bind=True,
    name="agentx.run_workflow",
    max_retries=3,
    default_retry_delay=15,
    soft_time_limit=DEFAULT_SOFT_LIMIT_SECONDS,
    time_limit=DEFAULT_HARD_LIMIT_SECONDS,
)
def run_workflow_task(self, task_id: str) -> dict:
    """Run one AGENTX workflow inside Celery's prefork worker."""
    try:
        from workflow.workflow import run_task_workflow
    except ImportError:
        logger.error("workflow.workflow.run_task_workflow not implemented yet")
        _run_async(_mark_task_finished(task_id, success=False, error="Workflow engine not implemented"))
        raise

    _run_async(_mark_task_started(task_id))

    try:
        result = _run_async(run_task_workflow(task_id))
        _run_async(_mark_task_finished(task_id, success=True))
        return result

    except SoftTimeLimitExceeded:
        logger.error("Task %s exceeded the %s-second soft time limit", task_id, DEFAULT_SOFT_LIMIT_SECONDS)
        _run_async(_mark_task_finished(
            task_id,
            success=False,
            error=f"Task exceeded its {DEFAULT_SOFT_LIMIT_SECONDS // 60}-minute time limit",
        ))
        raise

    except (OllamaUnavailableError, GovernanceUnavailableError) as exc:
        logger.warning("Transient failure on task %s, retrying: %s", task_id, exc)
        raise self.retry(exc=exc)

    except Exception as exc:
        logger.exception("Task %s failed", task_id)
        _run_async(_mark_task_finished(task_id, success=False, error=str(exc)))
        raise
