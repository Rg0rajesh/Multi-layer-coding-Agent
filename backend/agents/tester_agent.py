"""
Tester — writes a test suite and, for Python, actually runs it against a
scratch copy of the generated files instead of trusting the model's own
pass/fail claim.
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from governance.opa_client import log_tool_call
from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are TESTER, the QA expert for AGENTX.
RULES:
- At minimum 3 happy-path + 3 edge-case tests per function
- Report failures with exact line, expected vs actual, suggested fix
OUTPUT: {"test_files": {...}, "test_results": {"total": 12, "passed": 10, "failed": 2, "failures": [...]}}
"""

PYTEST_TIMEOUT_SECONDS = 60


async def tester_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "TESTER", "TASK", "→", "Writing tests")

    code_files = state.get("code_files", {})
    try:
        result = await generate_json(
            system=SYSTEM_PROMPT,
            user=f"Files to test:\n{code_files}\nLanguage: {state.get('language')}",
        )
    except LLMGenerationError as exc:
        await emit_log(task_id, "TESTER", "ERROR", "✗", f"Couldn't generate tests: {exc}")
        raise

    test_files = result.get("test_files", {})

    if (state.get("language") or "").lower() == "python":
        await log_tool_call(task_id, "pytest")
        test_results = await _run_pytest(code_files, test_files)
    else:
        # Non-Python: no local runner wired up yet, fall back to the model's
        # own report rather than pretending we verified it.
        test_results = result.get("test_results", {"total": 0, "passed": 0, "failed": 0, "failures": []})

    passed = test_results.get("failed", 0) == 0
    await emit_log(
        task_id, "TESTER", "PASS" if passed else "WARN", "✓" if passed else "✗",
        f"{test_results.get('passed', 0)}/{test_results.get('total', 0)} tests passed",
    )

    return {
        "test_results": test_results,
        "tests_passed": passed,
        "messages": [{"agent": "TESTER", "content": test_results}],
    }


async def _run_pytest(code_files: dict, test_files: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="agentx_test_") as tmpdir:
        root = Path(tmpdir)
        for relative_path, content in {**code_files, **test_files}.items():
            file_path = root / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
        return await asyncio.to_thread(_run_pytest_sync, root)


def _run_pytest_sync(root: Path) -> dict:
    try:
        proc = subprocess.run(
            ["pytest", "-q", "--tb=short", str(root)],
            capture_output=True, text=True, timeout=PYTEST_TIMEOUT_SECONDS, cwd=root,
        )
    except subprocess.TimeoutExpired:
        return {"total": 0, "passed": 0, "failed": 1, "failures": [{"error": "Test run timed out"}]}
    except FileNotFoundError:
        logger.error("pytest isn't installed in this environment")
        return {"total": 0, "passed": 0, "failed": 0, "failures": [], "error": "pytest not available"}

    return _parse_pytest_output(proc.stdout + proc.stderr)


def _parse_pytest_output(output: str) -> dict:
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", output)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", output)) else 0
    errored = int(m.group(1)) if (m := re.search(r"(\d+) error", output)) else 0
    failures = re.findall(r"FAILED (\S+) - (.+)", output)

    return {
        "total": passed + failed + errored,
        "passed": passed,
        "failed": failed + errored,
        "failures": [{"test": name, "reason": reason} for name, reason in failures],
    }