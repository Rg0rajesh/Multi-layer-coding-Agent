
"""
Thin wrapper around Bandit for scanning generated Python for the usual
suspects — hardcoded secrets, shell=True, eval(), insecure deserialization,
that kind of thing. Runs against a scratch copy so we're never touching
the real filesystem.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SECONDS = 45


async def scan(files: dict[str, str]) -> list[dict]:
    """files is {relative_path: content}. Only .py files get written out —
    Bandit has nothing to say about anything else."""
    py_files = {path: content for path, content in files.items() if path.endswith(".py")}
    if not py_files:
        return []

    with tempfile.TemporaryDirectory(prefix="bandit_") as tmpdir:
        root = Path(tmpdir)
        for relative_path, content in py_files.items():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        return await asyncio.to_thread(_run, root)


def _run(root: Path) -> list[dict]:
    try:
        proc = subprocess.run(
            ["bandit", "-r", str(root), "-f", "json"],
            capture_output=True,
            text=True,
            timeout=SCAN_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        logger.warning("bandit isn't on PATH — skipping the scan")
        return []
    except subprocess.TimeoutExpired:
        return [{"tool": "bandit", "severity": "MEDIUM", "message": "Scan timed out after 45s"}]

    # Bandit exits non-zero the moment it finds anything, so returncode
    # isn't a useful gate here — just try to parse whatever's on stdout.
    if not proc.stdout:
        return []

    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        logger.error("Bandit produced unparseable output: %s", proc.stdout[:200])
        return []

    return [_to_finding(issue) for issue in report.get("results", [])]


def _to_finding(issue: dict) -> dict:
    return {
        "tool": "bandit",
        "severity": issue["issue_severity"],
        "file": issue["filename"],
        "line": issue["line_number"],
        "message": issue["issue_text"],
        "rule_id": issue.get("test_id"),
        "suggestion": f"See {issue.get('more_info', 'the Bandit docs')} for a safer pattern.",
    }