
"""
Quality Agent's tool. Pylint isn't a gatekeeper the way Bandit/Semgrep are —
a style nit shouldn't bounce code back to Coder — so this just produces a
report the Reviewer can factor in.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 45

# Pylint's message types, mapped onto the HIGH/MEDIUM/LOW scale everyone
# else uses so the Reviewer doesn't need to know pylint-specific terms.
_TYPE_SEVERITY = {
    "fatal": "HIGH",
    "error": "HIGH",
    "warning": "MEDIUM",
    "refactor": "MEDIUM",
    "convention": "LOW",
}

# Rough per-issue penalty for a 0-10 score. Pylint's real scoring formula
# is tied to the text reporter and a pain to pull out alongside JSON —
# this is close enough for what the Reviewer actually does with it.
_PENALTY = {"HIGH": 1.0, "MEDIUM": 0.4, "LOW": 0.1}


async def check(files: dict[str, str]) -> dict:
    py_files = {path: content for path, content in files.items() if path.endswith(".py")}
    if not py_files:
        return {"score": 10.0, "issues": []}

    with tempfile.TemporaryDirectory(prefix="pylint_") as tmpdir:
        root = Path(tmpdir)
        for relative_path, content in py_files.items():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        issues = await asyncio.to_thread(_run, root)

    score = round(max(0.0, 10.0 - sum(_PENALTY[i["severity"]] for i in issues)), 1)
    return {"score": score, "issues": issues}


def _run(root: Path) -> list[dict]:
    try:
        proc = subprocess.run(
            # C0114-C0116 = missing module/class/function docstrings — noisy
            # given how AGENTX's own generated code isn't docstring-per-function.
            ["pylint", str(root), "--output-format=json", "--disable=C0114,C0115,C0116"],
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        logger.warning("pylint isn't on PATH — skipping the check")
        return []
    except subprocess.TimeoutExpired:
        return [{"tool": "pylint", "severity": "MEDIUM", "message": "Check timed out after 45s"}]

    if not proc.stdout:
        return []

    try:
        messages = json.loads(proc.stdout)
    except json.JSONDecodeError:
        logger.error("Pylint produced unparseable output: %s", proc.stdout[:200])
        return []

    return [_to_finding(msg) for msg in messages]


def _to_finding(msg: dict) -> dict:
    return {
        "tool": "pylint",
        "severity": _TYPE_SEVERITY.get(msg["type"], "LOW"),
        "file": msg["path"],
        "line": msg["line"],
        "message": msg["message"],
        "rule_id": msg.get("symbol", msg.get("message-id")),
    }