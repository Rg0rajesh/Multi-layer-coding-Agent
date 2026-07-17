# backend/celery_worker.py
"""
Celery entrypoint for AGENTX's background task execution.

This file owns exactly one job: take a task_id off the queue, run the
agent workflow against it, and make sure the DB reflects what happened.
It does not know anything about Planner/Coder/Tester internals — that
lives in workflow/workflow.py (Step 8) and is imported lazily below.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from celery import Celery
from celery.signals import worker_process_init
from celery.exceptions import SoftTimeLimitExceeded

from config import settings
from database import async_session_factory, engine
from models.task import Task
from models.log_entry import LogEntry

logger = logging.getLogger(__name__)

celery_app = Celery(
    "agentx",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # A task is only acked after it finishes. If the worker gets OOM-killed
    # (Ollama + Postgres + Redis + Chroma all fighting for RAM on a laptop
    # is a real scenario here), the job goes back on the queue instead of
    # vanishing.
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Recycle workers periodically — long-lived processes that keep opening
    # HTTP clients to Ollama/Chroma tend to creep in memory over a day.
    worker_max_tasks_per_child=50,
    worker_prefetch_multiplier=1,  # don't let one worker hoard several long jobs
)

# Hard ceiling if a task doesn't set its own limit. Individual jobs override
# this via apply_async(soft_time_limit=...) based on Task.max_exec_minutes.
DEFAULT_SOFT_LIMIT_SECONDS = 20 * 60
DEFAULT_HARD_LIMIT_SECONDS = 25 * 60


class TransientWorkflowError(Exception):
    """
    Raised by the workflow layer for failures worth retrying — Ollama not
    warmed up yet, a dropped DB connection, etc. Anything else raised out
    of run_task_workflow is treated as a genuine failure and NOT retried,
    since retrying a bad Planner output just burns tokens for the same
    result.
    """


# ---------------------------------------------------------------------------
# Event loop lifecycle
#
# Celery's default pool forks worker processes. database.py creates its
# AsyncEngine (and asyncpg's connection pool) once, at import time, in the
# parent process — those connections are bound to the parent's event loop.
# After fork, a child using them directly will either hang or throw
# "attached to a different loop". Fix: dispose the inherited pool right
# after fork so each child lazily builds its own, tied to its own loop.
# ---------------------------------------------------------------------------

_worker_loop: asyncio.AbstractEventLoop | None = None


@worker_process_init.connect
def _init_worker_process(**_kwargs) -> None:
    global _worker_loop
    _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    _worker_loop.run_until_complete(engine.dispose())
    logger.info("Worker process initialized, connection pool reset post-fork")


def _run_async(coro):
    """Runs a coroutine on this worker's dedicated loop, reusing it across
    tasks instead of spinning up a fresh loop (and asyncpg pool) per job."""
    loop = _worker_loop or asyncio.get_event_loop()
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _mark_task_started(task_id: str) -> None:
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found — was it deleted before the worker picked it up?")
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await db.commit()


async def _mark_task_finished(task_id: str, *, success: bool, error: str | None = None) -> None:
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return  # nothing to update — task was deleted mid-run

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
                message=error[:2000],  # log_entries.message has no hard cap, but keep rows sane
                severity="critical",
            ))

        await db.commit()


# ---------------------------------------------------------------------------
# The actual task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="agentx.run_workflow",
    max_retries=3,
    default_retry_delay=15,
    soft_time_limit=DEFAULT_SOFT_LIMIT_SECONDS,
    time_limit=DEFAULT_HARD_LIMIT_SECONDS,
)
def run_workflow_task(self, task_id: str) -> dict:
    """
    Entry point Celery calls. Kept synchronous on the outside (Celery's
    prefork pool expects that) and bridges into the async workflow via
    _run_async. Import of run_task_workflow is deliberately deferred to
    call time so this module can be imported (and the Celery app started)
    even before workflow/workflow.py has real content.
    """
    try:
        from workflow.workflow import run_task_workflow  # Step 8 boundary
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
        _run_async(_mark_task_finished(task_id, success=False, error="Task exceeded its time limit"))
        raise

    except TransientWorkflowError as exc:
        logger.warning("Transient failure on task %s, retrying: %s", task_id, exc)
        raise self.retry(exc=exc)

    except Exception as exc:  # noqa: BLE001 — genuinely broad: this is the last line of defense
        logger.exception("Task %s failed", task_id)
        _run_async(_mark_task_finished(task_id, success=False, error=str(exc)))
        raise