"""
Coder — writes the implementation from an approved plan, and on a retry,
patches only what Tester or Security flagged instead of regenerating
everything.
"""
from __future__ import annotations

import logging

from governance.opa_client import log_tool_call
from services.llm_service import LLMGenerationError, generate_json
from services.log_service import emit_log
from workflow.state import WorkflowState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are CODER, the code generation expert for AGENTX.
RULES:
- Follow the exact plan; write complete files, no TODOs
- Follow language best practices (PEP8 / ESLint)
- Fix only what feedback flags on retry, don't rewrite everything
OUTPUT: {"src/server.ts": "// code...", "src/routes.ts": "..."}
"""


async def coder_node(state: WorkflowState) -> dict:
    task_id = state["task_id"]
    retry_count = state.get("coder_retries", 0)
    is_retry = retry_count > 0

    await emit_log(
        task_id, "CODER", "TASK", "→",
        f"Fixing flagged issues (retry {retry_count})" if is_retry else "Writing implementation",
    )

    try:
        new_files = await generate_json(system=SYSTEM_PROMPT, user=_build_prompt(state, is_retry))
    except LLMGenerationError as exc:
        await emit_log(task_id, "CODER", "ERROR", "✗", f"Generation failed: {exc}")
        raise

    # Coder runs under the credential Identity Broker issued (workflow.py
    # puts identity_broker right before coder in the graph). A path that
    # escapes the workspace never gets written, no matter what the model
    # produced — that's the one thing Identity Broker's scope actually
    # exists to stop, so it's worth checking again here rather than trusting
    # the model kept to the plan. Everything else still gets written; the
    # rest of the scope is advisory bookkeeping, not a strict per-file
    # whitelist (see derive_scope() in governance/opa_client.py).
    accepted_files = {}
    for file_path, content in new_files.items():
        in_scope = await log_tool_call(task_id, "file_write", target=file_path)
        if _escapes_workspace(file_path):
            await emit_log(task_id, "CODER", "ERROR", "✗", f"Refused to write outside the workspace: {file_path}")
            continue
        if not in_scope:
            logger.info("File %s written outside the token's declared tool scope for task %s", file_path, task_id)
        accepted_files[file_path] = content

    # Merge, don't clobber — files that already passed shouldn't disappear
    # just because this call only touched two of them.
    code_files = {**state.get("code_files", {}), **accepted_files}
    total_lines = sum(content.count("\n") + 1 for content in code_files.values())

    await emit_log(
        task_id, "CODER", "PASS", "✓", f"{len(accepted_files)} file(s) written, {total_lines} lines total"
    )

    return {
        "code_files": code_files,
        "coder_retries": retry_count + 1 if is_retry else retry_count,
        "messages": [{"agent": "CODER", "content": {"files_touched": list(accepted_files.keys())}}],
    }


def _escapes_workspace(file_path: str) -> bool:
    return file_path.startswith("/") or ".." in file_path.split("/")


def _build_prompt(state: WorkflowState, is_retry: bool) -> str:
    if not is_retry:
        return (
            f"Plan:\n{state.get('plan', {})}\n\n"
            f"Task: {state['task_description']}\nLanguage: {state.get('language') or 'unspecified'}"
        )

    return (
        f"Existing files:\n{state.get('code_files', {})}\n\n"
        f"Fix ONLY what's listed below. Leave everything else untouched.\n\nFeedback:\n{_feedback(state)}"
    )


def _feedback(state: WorkflowState) -> str:
    notes = []
    if (results := state.get("test_results")) and results.get("failures"):
        notes.append(f"Test failures: {results['failures']}")
    if not state.get("safety_passed", True) and (report := state.get("safety_report")):
        notes.append(f"Security findings: {report.get('findings', [])}")
    return "\n".join(notes) or "No specific feedback recorded — recheck the plan against the code."