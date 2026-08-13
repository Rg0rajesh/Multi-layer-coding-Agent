"""
Coder — writes the implementation from an approved plan and, on retry,
patches only the issues reported by Tester or Security.
"""
from __future__ import annotations

import logging

from governance.opa_client import log_tool_call
from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are CODER, the implementation expert for AGENTX.

RETURN ONLY ONE VALID JSON OBJECT.
Never return markdown, code fences, explanations, or text outside the JSON.

Required output shape:
{
  "relative/path/to/file.py": "complete source code as a JSON string",
  "another/file.py": "complete source code as a JSON string"
}

Rules:
- Keys must be relative workspace file paths.
- Values must be complete source-code strings.
- Follow the approved plan exactly.
- Generate real, executable implementation code.
- Do not return summaries instead of code.
- Do not return TODOs or placeholders.
- Do not invent a file format that the plan does not require.
- On retry, modify only the files necessary to fix the supplied feedback.
- Keep imports, syntax, and dependencies consistent with the requested language.
- The JSON must start with { and end with }.
"""


async def coder_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    retry_count = state.get("coder_retries", 0)
    is_retry = retry_count > 0

    await emit_log(
        task_id,
        "CODER",
        "TASK",
        "→",
        f"Fixing flagged issues (retry {retry_count})" if is_retry else "Writing implementation",
    )

    try:
        new_files = await generate_json(
            system=SYSTEM_PROMPT,
            user=_build_prompt(state, is_retry),
            temperature=0.0,
        )
    except LLMGenerationError as exc:
        raw = exc.raw_response[:1000] if exc.raw_response else ""
        logger.error("Coder JSON generation failed: %s; raw=%r", exc, raw)
        await emit_log(
            task_id,
            "CODER",
            "ERROR",
            "✗",
            "Generation failed: model did not return valid JSON after retries",
        )
        raise

    if not isinstance(new_files, dict) or not new_files:
        raise LLMGenerationError(
            "Coder returned no files",
            raw_response=str(new_files),
        )

    accepted_files: dict[str, str] = {}

    for file_path, content in new_files.items():
        if not isinstance(file_path, str) or not isinstance(content, str):
            logger.warning("Ignoring malformed coder output entry: %r", file_path)
            continue

        if _escapes_workspace(file_path):
            await emit_log(
                task_id,
                "CODER",
                "ERROR",
                "✗",
                f"Refused to write outside the workspace: {file_path}",
            )
            continue

        in_scope = await log_tool_call(task_id, "file_write", target=file_path)
        if not in_scope:
            logger.info(
                "File %s is outside the token's declared tool scope for task %s",
                file_path,
                task_id,
            )

        accepted_files[file_path] = content

    if not accepted_files:
        raise LLMGenerationError(
            "Coder produced no valid in-workspace files",
            raw_response=str(new_files),
        )

    code_files = {**state.get("code_files", {}), **accepted_files}
    total_lines = sum(content.count("\n") + 1 for content in code_files.values())

    await emit_log(
        task_id,
        "CODER",
        "PASS",
        "✓",
        f"{len(accepted_files)} file(s) written, {total_lines} lines total",
    )

    return {
        "code_files": code_files,
        "coder_retries": retry_count + 1 if is_retry else retry_count,
        "messages": [
            {
                "agent": "CODER",
                "content": {"files_touched": list(accepted_files.keys())},
            }
        ],
    }


def _escapes_workspace(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/")
    return normalized.startswith("/") or normalized == ".." or normalized.startswith("../") or "/../" in normalized


def _build_prompt(state: WorkflowState, is_retry: bool) -> str:
    if not is_retry:
        return (
            "Approved plan:\n"
            f"{state.get('plan', {})}\n\n"
            "Task:\n"
            f"{state['task_description']}\n\n"
            "Language:\n"
            f"{state.get('language') or 'unspecified'}\n\n"
            "Return complete implementation files as ONE JSON object."
        )

    return (
        "Existing generated files:\n"
        f"{state.get('code_files', {})}\n\n"
        "Fix ONLY the problems listed below. Keep all unrelated code unchanged.\n\n"
        "Feedback:\n"
        f"{_feedback(state)}\n\n"
        "Return only the complete replacement files needed for the fix as ONE JSON object."
    )


def _feedback(state: WorkflowState) -> str:
    notes: list[str] = []

    results = state.get("test_results")
    if isinstance(results, dict) and results.get("failures"):
        notes.append(f"Test failures: {results['failures']}")

    if not state.get("safety_passed", True):
        report = state.get("safety_report")
        if report:
            findings = report.get("findings", []) if isinstance(report, dict) else report
            notes.append(f"Security findings: {findings}")

    return "\n".join(notes) or "No specific feedback recorded — recheck the plan against the code."
