"""
Semgrep catches what Bandit's rule set doesn't — broader OWASP-style
patterns and whatever the `auto` ruleset pulls in for the detected
language. Same scratch-dir approach as bandit_scanner.
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

# Semgrep's severities don't match Bandit's naming, so translate onto the
# HIGH/MEDIUM/LOW scale the rest of the pipeline already expects.
_SEVERITY_MAP = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}


async def scan(files: dict[str, str]) -> list[dict]:
    if not files:
        return []

    with tempfile.TemporaryDirectory(prefix="semgrep_") as tmpdir:
        root = Path(tmpdir)
        for relative_path, content in files.items():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        return await asyncio.to_thread(_run, root)


def _run(root: Path) -> list[dict]:
    try:
        proc = subprocess.run(
            ["semgrep", "--config=auto", "--json", "--quiet", str(root)],
            capture_output=True,
            text=True,
            timeout=SCAN_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        logger.warning("semgrep isn't on PATH — skipping the scan")
        return []
    except subprocess.TimeoutExpired:
        return [{"tool": "semgrep", "severity": "MEDIUM", "message": "Scan timed out after 45s"}]

    if not proc.stdout:
        return []

    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        logger.error("Semgrep produced unparseable output: %s", proc.stdout[:200])
        return []

    return [_to_finding(result) for result in report.get("results", [])]


def _to_finding(result: dict) -> dict:
    extra = result["extra"]
    return {
        "tool": "semgrep",
        "severity": _SEVERITY_MAP.get(extra["severity"], "LOW"),
        "file": result["path"],
        "line": result["start"]["line"],
        "message": extra["message"],
        "rule_id": result.get("check_id"),
        "suggestion": extra.get("fix", "No auto-fix available — review manually."),
    }
