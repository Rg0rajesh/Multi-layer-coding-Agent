
# backend/evaluation/metrics.py
"""
Workflow-centric metrics (C5) plus the two v2 additions we can actually
compute today (C6 partial, C7). Jailbreak Resistance (C9) isn't a
per-task number — see jailbreak_resistance_score() at the bottom — so it
doesn't show up in WorkflowMetrics until the adversarial eval set exists.

None of this touches pass/fail. That's SWE-bench's job. This answers a
different question: was the process any good getting there.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent_run import AgentRun
from models.curated_memory import CuratedMemory
from models.identity_token import IdentityToken
from models.task import Task

# Both re-plans and coder retries stop mattering much past this point —
# a task that's replanned 8 times is just as "bad" on this axis as one
# replanned 5 times, so there's no point letting the score go negative.
REPLAN_SATURATION = 5
RETRY_SATURATION = 5


@dataclass
class WorkflowMetrics:
    task_id: UUID

    planning_quality: float          # 0-10, higher = fewer/cleaner re-plans
    coordination_efficiency: float   # 0-10, active agent time / wall clock
    memory_effectiveness: float      # 0-10, proxy — see _memory_effectiveness
    safety_improvement: float        # 0-10, issues caught per 1k lines
    human_interventions: int         # raw count, deliberately not normalized

    permission_scope_violations: int
    memory_curation_precision: float | None  # None until the labeled eval set exists

    def as_dict(self) -> dict:
        return {
            "planning_quality": self.planning_quality,
            "coordination_efficiency": self.coordination_efficiency,
            "memory_effectiveness": self.memory_effectiveness,
            "safety_improvement": self.safety_improvement,
            "human_interventions": self.human_interventions,
            "permission_scope_violations": self.permission_scope_violations,
            "memory_curation_precision": self.memory_curation_precision,
        }


async def compute_task_metrics(db: AsyncSession, *, task_id: UUID) -> WorkflowMetrics:
    task = await db.get(Task, task_id)
    if task is None:
        raise ValueError(f"Task {task_id} not found")

    agent_runs, memory_score, scope_violations = await asyncio.gather(
        _get_agent_runs(db, task_id),
        _memory_effectiveness(db, task),
        _scope_violations(db, task_id),
    )

    return WorkflowMetrics(
        task_id=task_id,
        planning_quality=_planning_quality(task),
        coordination_efficiency=_coordination_efficiency(task, agent_runs),
        memory_effectiveness=memory_score,
        safety_improvement=_safety_improvement(task),
        human_interventions=task.human_interventions,
        permission_scope_violations=scope_violations,
        memory_curation_precision=None,  # eval-set level — annotators haven't labeled anything yet
    )


async def _get_agent_runs(db: AsyncSession, task_id: UUID) -> list[AgentRun]:
    result = await db.execute(select(AgentRun).where(AgentRun.task_id == task_id))
    return list(result.scalars().all())


def _planning_quality(task: Task) -> float:
    # A re-plan means Human rejected the plan outright. Not every re-plan is
    # a failure — some tasks are genuinely ambiguous on the first pass — so
    # this decays rather than zeroing out after one.
    penalty = min(task.replan_count, REPLAN_SATURATION) / REPLAN_SATURATION
    return round(10.0 * (1 - penalty), 2)


def _coordination_efficiency(task: Task, agent_runs: list[AgentRun]) -> float:
    """Active agent compute time vs. total wall clock. A slow Ollama
    cold-start or a long human-approval wait shows up here as overhead even
    though nothing was technically duplicated — that's intentional, waiting
    is still a coordination cost."""
    total_elapsed_ms = task.elapsed_seconds * 1000
    if total_elapsed_ms <= 0:
        return 0.0
    active_ms = sum(run.duration_ms or 0 for run in agent_runs)
    return round(min(active_ms / total_elapsed_ms, 1.0) * 10, 2)


async def _memory_effectiveness(db: AsyncSession, task: Task) -> float:
    """Proxy metric, not a direct measurement: projects with known_bug
    entries already curated, combined with a low coder-retry count on this
    task, suggest the Coder didn't re-trip over something we'd already
    seen. Weak signal on its own — the real test is the C1 ablation study
    (same task, memory on vs. off) once experiments start."""
    if task.project_id is None:
        return 0.0

    known_bug_count = await db.scalar(
        select(func.count()).where(
            CuratedMemory.project_id == task.project_id,
            CuratedMemory.tag == "known_bug",
        )
    )
    if not known_bug_count:
        return 5.0  # no project history to have leveraged either way — neutral, not zero

    retry_penalty = min(task.coder_retries, RETRY_SATURATION) / RETRY_SATURATION
    return round(10.0 * (1 - retry_penalty), 2)


def _safety_improvement(task: Task) -> float:
    """Zero vulnerabilities found isn't the best possible score — that's
    indistinguishable from nobody looking. This rewards catching issues per
    line written, since a pipeline without Security agents wouldn't catch
    anything at all. The actual baseline comparison (with vs. without
    Security) happens in the ablation study, not in this number alone."""
    if task.total_lines_written == 0:
        return 0.0
    catch_rate_per_1k = task.safety_issues_found / task.total_lines_written * 1000
    return round(min(catch_rate_per_1k, 10.0), 2)


async def _scope_violations(db: AsyncSession, task_id: UUID) -> int:
    """Counts tool calls made under an Identity Broker token that fell
    outside the token's granted scope. tool_call_log is append-only, so
    this is just a filter — no aggregation trick needed here."""
    tokens = (
        await db.execute(select(IdentityToken).where(IdentityToken.task_id == task_id))
    ).scalars().all()

    violations = 0
    for token in tokens:
        allowed_tools = set(token.scope.get("tools", []))
        for call in token.tool_call_log:
            if call.get("tool") not in allowed_tools:
                violations += 1
    return violations


# ---------------------------------------------------------------------------
# Eval-set level metrics — these compare across a batch of tasks, not one.
# Neither belongs on WorkflowMetrics because a single task can't answer
# "did Guardrail resist a multi-turn jailbreak attempt" on its own.
# ---------------------------------------------------------------------------

async def jailbreak_resistance_score(
    db: AsyncSession, *, adversarial_task_ids: list[UUID]
) -> float:
    """Block rate across a known-adversarial task set. Requires someone to
    have actually built and labeled that set (SWE-bench runner, Step 26) —
    there's no way to infer "this was an attack attempt" from
    session_risk_scores alone."""
    if not adversarial_task_ids:
        raise ValueError("Need at least one labeled adversarial task to score against")

    from models.session_risk import SessionRiskScore  # narrow import, only used here

    result = await db.execute(
        select(func.count()).where(
            SessionRiskScore.task_id.in_(adversarial_task_ids),
            SessionRiskScore.last_verdict == "block",
        )
    )
    blocked = result.scalar() or 0
    return round(blocked / len(adversarial_task_ids), 3)


async def batch_average(db: AsyncSession, *, task_ids: list[UUID]) -> dict:
    """Averages WorkflowMetrics across a set of tasks — what the paper's
    baseline-comparison tables actually need. One round trip per task
    rather than a single mega-query; task counts in a SWE-bench subset
    run in the dozens to low hundreds, so this stays well within a
    reasonable request budget without the join complexity of doing it
    in SQL."""
    if not task_ids:
        return {}

    results = await asyncio.gather(*(compute_task_metrics(db, task_id=tid) for tid in task_ids))

    numeric_fields = [
        "planning_quality", "coordination_efficiency", "memory_effectiveness",
        "safety_improvement", "human_interventions", "permission_scope_violations",
    ]
    return {
        field: round(sum(getattr(m, field) for m in results) / len(results), 3)
        for field in numeric_fields
    }