"""Tester generates executable tests and runs them in a bounded scratch workspace."""
from __future__ import annotations

import asyncio
import logging
import os
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

RETURN ONLY ONE VALID JSON OBJECT.
Never return markdown, code fences, explanations, or text outside the JSON.

Required JSON shape:
{
  "test_files": {"tests/test_example.py": "complete executable pytest source code"},
  "test_results": {"total": 0, "passed": 0, "failed": 0, "failures": []}
}

Rules:
- Test the actual functions/classes present in the supplied implementation.
- Include normal, edge, and invalid-input cases when applicable.
- Do not invent APIs.
- Never use network access, subprocess execution, shell commands, or system administration in generated tests.
- test_results is only an initial model report; AGENTX executes pytest itself.
"""

PYTEST_TIMEOUT_SECONDS = 60
MAX_TEST_SOURCE_BYTES = 100_000
_BLOCKED_TEST_PATTERNS = re.compile(
    r"(?:\b(?:subprocess|socket|ctypes|multiprocessing)\b|\bos\.system\b|\bos\.popen\b|\brequests\b|\bhttpx\b)",
    re.IGNORECASE,
)


async def tester_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    await emit_log(task_id, "TESTER", "TASK", "→", "Writing tests")
    code_files = state.get("code_files", {})

    try:
        result = await generate_json(
            system=SYSTEM_PROMPT,
            user=(
                "Implementation files to test:\n"
                f"{code_files}\n\n"
                f"Language: {state.get('language') or 'python'}\n\n"
                "Generate complete executable test files as ONE JSON object."
            ),
            temperature=0.0,
        )
    except LLMGenerationError as exc:
        await emit_log(task_id, "TESTER", "ERROR", "✗", "Couldn't generate tests: model did not return valid JSON after retries")
        logger.error("Tester JSON generation failed: %s; raw=%r", exc, exc.raw_response[:1000] if exc.raw_response else "")
        raise

    test_files = result.get("test_files", {})
    if not isinstance(test_files, dict) or not test_files:
        raise LLMGenerationError("Tester returned no test files", raw_response=str(result))

    clean_test_files: dict[str, str] = {}
    for path, content in test_files.items():
        normalized = path.replace("\\", "/") if isinstance(path, str) else ""
        if not normalized or not isinstance(content, str):
            continue
        if normalized.startswith("/") or ".." in normalized.split("/"):
            logger.warning("Ignoring unsafe tester path: %s", path)
            continue
        if len(content.encode("utf-8")) > MAX_TEST_SOURCE_BYTES:
            logger.warning("Ignoring oversized test file: %s", path)
            continue
        if _BLOCKED_TEST_PATTERNS.search(content):
            logger.warning("Ignoring test file containing blocked execution/network primitives: %s", path)
            continue
        clean_test_files[normalized] = content

    if not clean_test_files:
        raise LLMGenerationError("Tester returned no safe test files", raw_response=str(result))

    if (state.get("language") or "").lower() == "python":
        authorized = await log_tool_call(task_id, "pytest")
        if not authorized:
            failure = {"total": 0, "passed": 0, "failed": 1, "failures": [{"error": "pytest denied by identity policy"}]}
            await emit_log(task_id, "TESTER", "ERROR", "✗", "Test execution denied by Identity Broker scope")
            return {"test_results": failure, "tests_passed": False, "messages": [{"agent": "TESTER", "content": failure}]}
        test_results = await _run_pytest(code_files, clean_test_files)
    else:
        test_results = result.get("test_results", {"total": 0, "passed": 0, "failed": 0, "failures": []})

    passed = test_results.get("failed", 0) == 0 and test_results.get("error") is None
    await emit_log(task_id, "TESTER", "PASS" if passed else "WARN", "✓" if passed else "✗", f"{test_results.get('passed', 0)}/{test_results.get('total', 0)} tests passed")
    return {"test_results": test_results, "tests_passed": passed, "messages": [{"agent": "TESTER", "content": test_results}]}


async def _run_pytest(code_files: dict, test_files: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="agentx_test_") as tmpdir:
        root = Path(tmpdir)
        for relative_path, content in {**code_files, **test_files}.items():
            file_path = root / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(str(content), encoding="utf-8")
        return await asyncio.to_thread(_run_pytest_sync, root)


def _resource_limits() -> None:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (45, 60))
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (5 * 1024 * 1024, 5 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except (ImportError, AttributeError, ValueError, OSError):
        pass


def _run_pytest_sync(root: Path) -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(root),
        "PYTHONHASHSEED": "0",
        "NO_PROXY": "*",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "ALL_PROXY": "",
    }
    try:
        proc = subprocess.run(
            ["pytest", "-q", "--tb=short", str(root)],
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT_SECONDS,
            cwd=root,
            env=env,
            preexec_fn=_resource_limits if os.name == "posix" else None,
        )
    except subprocess.TimeoutExpired:
        return {"total": 0, "passed": 0, "failed": 1, "failures": [{"error": "Test run timed out"}]}
    except FileNotFoundError:
        logger.error("pytest isn't installed in this environment")
        return {"total": 0, "passed": 0, "failed": 1, "failures": [{"error": "pytest not available"}]}

    return _parse_pytest_output(proc.stdout + proc.stderr)


def _parse_pytest_output(output: str) -> dict:
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", output)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", output)) else 0
    errored = int(m.group(1)) if (m := re.search(r"(\d+) error", output)) else 0
    skipped = int(m.group(1)) if (m := re.search(r"(\d+) skipped", output)) else 0
    failures = re.findall(r"FAILED (\S+) - (.+)", output)
    return {
        "total": passed + failed + errored + skipped,
        "passed": passed,
        "failed": failed + errored,
        "skipped": skipped,
        "failures": [{"test": name, "reason": reason} for name, reason in failures],
    }
