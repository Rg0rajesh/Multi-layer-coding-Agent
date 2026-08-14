"""Coder — writes the implementation from an approved plan and persists each file as it is authorized."""
from __future__ import annotations

import logging

from governance.opa_client import log_tool_call
from memory.memory_manager import MemoryManager
from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState
from database import async_session_factory
from models.code_output import CodeOutput

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are CODER, the implementation expert for AGENTX.

RETURN ONLY ONE VALID JSON OBJECT.
Never return markdown, code fences, explanations, or text outside JSON.

Required output shape:
{
  "relative/path/to/file.ext": "complete source code as a JSON string"
}

Rules:
- Keys must be relative workspace file paths.
- Values must be complete source-code strings.
- Follow the approved plan exactly.
- Generate real executable implementation code.
- Do not return summaries, TODOs, or placeholders.
- Keep imports, syntax, and dependencies consistent with the requested language.
- The JSON must start with { and end with }.
"""


async def coder_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    retry_count = state.get("coder_retries", 0)
    is_retry = retry_count > 0
    await emit_log(task_id, "CODER", "TASK", "→", f"Fixing flagged issues (retry {retry_count})" if is_retry else "Writing implementation")

    try:
        new_files = await generate_json(system=SYSTEM_PROMPT, user=await _build_prompt(state, is_retry), temperature=0.0)
    except LLMGenerationError as exc:
        await emit_log(task_id, "CODER", "ERROR", "✗", "Generation failed: model did not return valid JSON after retries")
        logger.error("Coder JSON generation failed: %s; raw=%r", exc, exc.raw_response[:1000] if exc.raw_response else "")
        raise

    if not isinstance(new_files, dict) or not new_files:
        raise LLMGenerationError("Coder returned no files", raw_response=str(new_files))

    accepted_files: dict[str, str] = {}
    denied_files: list[str] = []
    for file_path, content in new_files.items():
        if not isinstance(file_path, str) or not isinstance(content, str):
            continue
        if _escapes_workspace(file_path):
            denied_files.append(file_path)
            await emit_log(task_id, "CODER", "ERROR", "✗", f"Refused unsafe path: {file_path}")
            continue
        if not await log_tool_call(task_id, "file_write", target=file_path):
            denied_files.append(file_path)
            await emit_log(task_id, "CODER", "ERROR", "✗", f"Refused out-of-scope write: {file_path}")
            continue

        accepted_files[file_path] = content
        await _persist_code_file(task_id, state.get("language"), file_path, content)
        await emit_log(task_id, "CODER", "WRITE", "•", f"Writing {file_path} ({content.count(chr(10)) + 1} lines)")

    if not accepted_files:
        raise LLMGenerationError("Coder produced no files authorized by the Identity Broker", raw_response=str(new_files))

    if denied_files:
        await emit_log(task_id, "CODER", "ERROR", "✗", f"Implementation incomplete — {len(denied_files)} requested file(s) were outside the approved scope")
        raise LLMGenerationError("Coder attempted files outside the approved Identity Broker scope", raw_response=str(denied_files))

    code_files = {**state.get("code_files", {}), **accepted_files}
    total_lines = sum(content.count("\n") + 1 for content in code_files.values())
    await emit_log(task_id, "CODER", "PASS", "✓", f"{len(accepted_files)} file(s) written, {total_lines} lines total")
    return {"code_files": code_files, "coder_retries": retry_count, "messages": [{"agent": "CODER", "content": {"files_touched": list(accepted_files.keys())}}]}


async def _persist_code_file(task_id: str, language: str | None, file_path: str, content: str) -> None:
    async with async_session_factory() as db:
        existing = await db.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(CodeOutput).where(
                CodeOutput.task_id == task_id, CodeOutput.file_path == file_path
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.content = content
            row.language = language
            row.line_count = content.count("\n") + 1
        else:
            db.add(CodeOutput(
                task_id=task_id,
                file_path=file_path,
                file_name=file_path.rsplit("/", 1)[-1],
                content=content,
                language=language,
                line_count=content.count("\n") + 1,
                is_test_file="test" in file_path.lower() or "/tests/" in file_path.lower(),
            ))
        await db.commit()


def _escapes_workspace(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/")
    return normalized.startswith("/") or normalized == ".." or normalized.startswith("../") or "/../" in normalized


async def _memory_prompt(state: WorkflowState) -> str:
    user_id = state.get("user_id")
    if not user_id:
        return ""
    manager = MemoryManager(task_id=state["task_id"], user_id=user_id, project_id=state.get("project_id"))
    try:
        context = await manager.build_agent_context(state.get("task_description", ""))
        block = context.as_prompt_block()
        return block if block else "No relevant long-term memory was retrieved."
    except Exception:
        logger.warning("Memory retrieval failed for coder task %s", state["task_id"], exc_info=True)
        return "Memory retrieval unavailable; rely only on the approved plan and supplied code."


async def _build_prompt(state: WorkflowState, is_retry: bool) -> str:
    memory = await _memory_prompt(state)
    if not is_retry:
        return f"Approved plan:\n{state.get('plan', {})}\n\nTask:\n{state['task_description']}\n\nLanguage:\n{state.get('language') or 'unspecified'}\n\nRelevant memory:\n{memory}\n\nReturn complete implementation files as ONE JSON object."
    return f"Existing generated files:\n{state.get('code_files', {})}\n\nRelevant memory:\n{memory}\n\nFix ONLY the problems listed below.\n\nFeedback:\n{_feedback(state)}\n\nReturn only complete replacement files needed for the fix as ONE JSON object."


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
