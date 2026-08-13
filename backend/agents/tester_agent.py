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

Return ONLY one valid JSON object. Do not use markdown or explanations.

Required JSON shape:
{
  "test_files": {
    "test_example.py": "complete test source code"
  },
  "test_results": {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "failures": []
  }
}

Rules:
- Generate executable pytest files for the supplied Python code.
- Aim for at least 3 happy-path and 3 edge-case tests per function when practical.
- Keep tests concise enough to fit the response.
- test_files values must contain complete source code strings.
- test_results is only the model's initial report; AGENTX will execute pytest itself.
- Never return text outside the JSON object.
"""

PYTEST_TIMEOUT_SECONDS = 60


async def tester_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "TESTER", "TASK", "→", "Writing tests")

    code_files = state.get("code_files", {})

    try:
        result = await generate_json(
            system=SYSTEM_PROMPT,
            user=(
                "Files to test:\n"
                f"{code_files}\n\n"
                f"Language: {state.get('language') or 'python'}\n\n"
                "Return the complete pytest test files as JSON."
            ),
            temperature=0.0,
        )
    except LLMGenerationError as exc:
        logger.error(
            "Tester JSON generation failed: %s; raw=%r",
            exc,
            exc.raw_response[:1000] if exc.raw_response else "",
        )
        await emit_log(
            task_id,
            "TESTER",
            "ERROR",
            "✗",
            "Couldn't generate tests: model did not return valid JSON after retry",
        )
        raise

    test_files = result.get("test_files", {})
    if not isinstance(test_files, dict):
        raise LLMGenerationError(
            "Tester returned an invalid test_files structure",
            raw_response=str(result),
        )

    if (state.get("language") or "").lower() == "python":
        await log_tool_call(task_id, "pytest")
        test_results = await _run_pytest(code_files, test_files)
    else:
        test_results = result.get(
            "test_results",
            {"total": 0, "passed": 0, "failed": 0, "failures": []},
        )

    passed = test_results.get("failed", 0) == 0
    await emit_log(
        task_id,
        "TESTER",
        "PASS" if passed else "WARN",
        "✓" if passed else "✗",
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
            file_path.write_text(str(content), encoding="utf-8")
        return await asyncio.to_thread(_run_pytest_sync, root)


def _run_pytest_sync(root: Path) -> dict:
    try:
        proc = subprocess.run(
            ["pytest", "-q", "--tb=short", str(root)],
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT_SECONDS,
            cwd=root,
        )
    except subprocess.TimeoutExpired:
        return {
            "total": 0,
            "passed": 0,
            "failed": 1,
            "failures": [{"error": "Test run timed out"}],
        }
    except FileNotFoundError:
        logger.error("pytest isn't installed in this environment")
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "failures": [],
            "error": "pytest not available",
        }

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
        "failures": [
            {"test": name, "reason": reason}
            for name, reason in failures
        ],
    }
