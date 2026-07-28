
"""
Security agent (C2) — scans code DURING the workflow, before it's ever
treated as done. Bandit and Semgrep run for real against a scratch copy
of the generated files; Pylint's output is left for the Reviewer since
style issues shouldn't block the way a hardcoded credential should.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path

from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SECONDS = 45
BLOCKING_SEVERITIES = {"HIGH", "MEDIUM"}  # LOW findings surface in the report but don't bounce back to Coder


async def security_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    code_files = state.get("code_files", {})
    await emit_log(task_id, "SECURITY", "TASK", "→", "Scanning generated code")

    py_files = {path: content for path, content in code_files.items() if path.endswith(".py")}
    if not py_files:
        await emit_log(task_id, "SECURITY", "PASS", "✓", "No Python files to scan")
        return {"safety_report": {"findings": []}, "safety_passed": True}

    with tempfile.TemporaryDirectory(prefix="agentx_scan_") as tmpdir:
        root = Path(tmpdir)
        for relative_path, content in py_files.items():
            file_path = root / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        bandit_findings, semgrep_findings = await asyncio.gather(_run_bandit(root), _run_semgrep(root))

    findings = bandit_findings + semgrep_findings
    blocking = [f for f in findings if f["severity"] in BLOCKING_SEVERITIES]
    passed = not blocking

    await emit_log(
        task_id, "SECURITY", "PASS" if passed else "ERROR", "✓" if passed else "✗",
        f"Clean — {len(findings)} low-severity note(s)" if passed
        else f"{len(blocking)} blocking issue(s) — sending back to Coder",
    )

    return {
        "safety_report": {"findings": findings},
        "safety_passed": passed,
        "messages": [{"agent": "SECURITY", "content": {"finding_count": len(findings)}}],
    }


async def _run_bandit(root: Path) -> list[dict]:
    try:
        proc = await asyncio.to_thread(
            subprocess.run, ["bandit", "-r", str(root), "-f", "json"],
            capture_output=True, text=True, timeout=SCAN_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        logger.warning("bandit isn't installed — skipping")
        return []
    except subprocess.TimeoutExpired:
        return [{"tool": "bandit", "severity": "MEDIUM", "message": "Scan timed out"}]

    try:
        report = json.loads(proc.stdout) if proc.stdout else {}
    except json.JSONDecodeError:
        return []

    return [
        {
            "tool": "bandit",
            "severity": issue["issue_severity"],
            "file": issue["filename"],
            "line": issue["line_number"],
            "message": issue["issue_text"],
            "suggestion": f"See {issue.get('more_info', 'Bandit docs')} for a safer pattern.",
        }
        for issue in report.get("results", [])
    ]


async def _run_semgrep(root: Path) -> list[dict]:
    try:
        proc = await asyncio.to_thread(
            subprocess.run, ["semgrep", "--config=auto", "--json", str(root)],
            capture_output=True, text=True, timeout=SCAN_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        logger.warning("semgrep isn't installed — skipping")
        return []
    except subprocess.TimeoutExpired:
        return [{"tool": "semgrep", "severity": "MEDIUM", "message": "Scan timed out"}]

    try:
        report = json.loads(proc.stdout) if proc.stdout else {}
    except json.JSONDecodeError:
        return []

    severity_map = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}
    return [
        {
            "tool": "semgrep",
            "severity": severity_map.get(result["extra"]["severity"], "LOW"),
            "file": result["path"],
            "line": result["start"]["line"],
            "message": result["extra"]["message"],
            "suggestion": result["extra"].get("fix", "No auto-fix available — review manually."),
        }
        for result in report.get("results", [])
    ]