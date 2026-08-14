"""Language-agnostic tester for AGENTX using the isolated Piston runner."""
from __future__ import annotations

import logging
import re

from governance.opa_client import log_tool_call
from services.code_execution import CodeExecutionError, execute_code
from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are TESTER, the QA expert for AGENTX.

RETURN ONLY ONE VALID JSON OBJECT.

Required JSON shape:
{
  "test_files": {"path/to/test.ext": "complete test source"},
  "test_runner": "complete executable test-runner source code",
  "test_filename": "the filename used to execute test_runner",
  "test_results": {"total": 0, "passed": 0, "failed": 0, "failures": []}
}

Rules:
- Test the actual implementation supplied by Coder.
- Include normal, edge and invalid-input cases where applicable.
- The test runner MUST be executable directly by the requested language runtime.
- For Java, use a public Main class in Main.java with assertions or explicit pass/fail output; do not require JUnit.
- For JavaScript/TypeScript, use built-in assertions or explicit checks; do not require npm packages.
- For C/C++, Go, Rust, PHP, Ruby and other compiled/interpreted languages, create a self-contained executable test runner using only the standard language/runtime facilities.
- For HTML/CSS, validate structure and syntax using deterministic checks and report failures; do not claim browser rendering was tested.
- For Python, pytest may be used only when available; otherwise the test_runner must remain executable with the Python runtime.
- Do not use network access, subprocess execution, shell commands, or system administration in generated tests.
- Do not invent APIs.
"""

_BLOCKED_TEST_PATTERNS = re.compile(r"(?:\b(?:subprocess|socket|ctypes|multiprocessing)\b|\bos\.system\b|\bos\.popen\b|\brequests\b|\bhttpx\b)", re.IGNORECASE)
MAX_TEST_SOURCE_BYTES = 100_000


async def tester_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    language = (state.get("language") or "python").lower()
    await emit_log(task_id, "TESTER", "TASK", "→", f"Testing {language} implementation")
    code_files = state.get("code_files", {})

    try:
        result = await generate_json(
            system=SYSTEM_PROMPT,
            user=(f"Implementation files:\n{code_files}\n\nLanguage: {language}\n\nGenerate complete executable tests as ONE JSON object."),
            temperature=0.0,
        )
    except LLMGenerationError:
        await emit_log(task_id, "TESTER", "ERROR", "✗", "Couldn't generate executable tests")
        raise

    test_files = result.get("test_files", {})
    runner = result.get("test_runner", "")
    filename = result.get("test_filename") or _default_test_filename(language)
    if not isinstance(test_files, dict) or not isinstance(runner, str) or not runner.strip():
        raise LLMGenerationError("Tester returned no executable test runner", raw_response=str(result))

    clean_files: dict[str, str] = {}
    for path, content in test_files.items():
        if not isinstance(path, str) or not isinstance(content, str):
            continue
        normalized = path.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/") or len(content.encode("utf-8")) > MAX_TEST_SOURCE_BYTES:
            continue
        if _BLOCKED_TEST_PATTERNS.search(content):
            continue
        clean_files[normalized] = content

    if _BLOCKED_TEST_PATTERNS.search(runner) or len(runner.encode("utf-8")) > MAX_TEST_SOURCE_BYTES:
        raise LLMGenerationError("Tester generated a blocked or oversized test runner", raw_response=runner)

    if language in {"html", "css"}:
        test_results = _static_test(language, code_files)
    else:
        if not await log_tool_call(task_id, "code_execute"):
            await emit_log(task_id, "TESTER", "ERROR", "✗", "Code execution denied by Identity Broker scope")
            return {"test_results": {"total": 0, "passed": 0, "failed": 1, "failures": [{"error": "code_execute denied"}]}, "tests_passed": False, "messages": []}
        try:
            execution = await execute_code(language=language, code=runner, filename=filename, extra_files=[{"name": p.rsplit("/", 1)[-1], "content": c} for p, c in {**code_files, **clean_files}.items()])
            test_results = _execution_results(execution)
        except CodeExecutionError as exc:
            test_results = {"total": 1, "passed": 0, "failed": 1, "failures": [{"error": str(exc)}]}

    passed = test_results.get("failed", 0) == 0 and test_results.get("error") is None
    await emit_log(task_id, "TESTER", "PASS" if passed else "WARN", "✓" if passed else "✗", f"{test_results.get('passed', 0)}/{test_results.get('total', 0)} tests passed")
    return {"test_results": test_results, "tests_passed": passed, "messages": [{"agent": "TESTER", "content": test_results}]}


def _default_test_filename(language: str) -> str:
    return {"python": "main_test.py", "javascript": "main.test.js", "typescript": "main.ts", "java": "Main.java", "c": "main.c", "c++": "main.cpp", "go": "main.go", "rust": "main.rs", "php": "main.php", "ruby": "main.rb"}.get(language, "main.txt")


def _execution_results(execution: dict) -> dict:
    output = execution.get("output", "")
    stderr = execution.get("stderr", "")
    success = bool(execution.get("success"))
    passed = len(re.findall(r"(?:PASS|passed|tests? passed)", output, re.IGNORECASE)) if success else 0
    if success and passed == 0:
        passed = 1
    return {"total": max(1, passed) if success else 1, "passed": passed if success else 0, "failed": 0 if success else 1, "failures": [] if success else [{"error": stderr or output or "Test runner failed"}], "stdout": output, "stderr": stderr}


def _static_test(language: str, code_files: dict) -> dict:
    source = "\n".join(str(v) for v in code_files.values())
    failures: list[dict] = []
    if language == "html":
        low = source.lower()
        if "<html" not in low and "<!doctype" not in low: failures.append({"error": "Missing HTML root"})
        if "<body" not in low: failures.append({"error": "Missing body element"})
    elif source.count("{") != source.count("}"):
        failures.append({"error": "Unbalanced CSS braces"})
    return {"total": 1, "passed": 0 if failures else 1, "failed": len(failures), "failures": failures}
