# backend/agents/security_agent.py
"""
Security agent (C2) — the safety gate between Coder and Reviewer.

This used to run Bandit/Semgrep itself, which meant the exact same
subprocess/tempdir dance lived here AND in safety/safety_guardian.py.
Guardian already does this properly (Bandit + Semgrep + Pylint, run
concurrently), so this node just calls it and translates the result
into workflow state. If you need to add a new scanner, add it to
safety_guardian.py — not here.
"""
from __future__ import annotations

import logging

from safety.safety_guardian import review
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)


async def security_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    code_files = state.get("code_files", {})

    await emit_log(task_id, "SECURITY", "TASK", "→", "Scanning generated code")

    py_files = {path: content for path, content in code_files.items() if path.endswith(".py")}
    if not py_files:
        await emit_log(task_id, "SECURITY", "PASS", "✓", "No Python files to scan")
        return {"safety_report": {"findings": [], "quality_score": 10.0}, "safety_passed": True}

    report = await review(py_files)
    blocking_count = len(report.blocking_findings())

    if report.passed:
        await emit_log(
            task_id, "SECURITY", "PASS", "✓",
            f"Clean — {len(report.findings)} low-severity note(s), quality {report.quality_score}/10",
        )
    else:
        await emit_log(
            task_id, "SECURITY", "ERROR", "✗",
            f"{blocking_count} blocking issue(s) — sending back to Coder",
        )

    return {
        "safety_report": {
            "findings": report.findings,
            "quality_score": report.quality_score,
            "quality_issues": report.quality_issues,
        },
        "safety_passed": report.passed,
        "messages": [{"agent": "SECURITY", "content": {"finding_count": len(report.findings)}}],
    }