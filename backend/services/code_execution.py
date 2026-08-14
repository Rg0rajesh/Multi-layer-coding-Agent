from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

LANGUAGE_ALIASES = {
    "js": "javascript",
    "jsx": "javascript",
    "node": "javascript",
    "ts": "typescript",
    "py": "python",
    "c++": "c++",
    "cpp": "c++",
    "cs": "csharp",
    "rb": "ruby",
}

SUPPORTED_STATIC = {"html", "css"}


class CodeExecutionError(Exception):
    pass


async def list_runtimes() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{settings.piston_url}/api/v2/runtimes")
        response.raise_for_status()
        return response.json()


def normalize_language(language: str) -> str:
    value = (language or "").strip().lower()
    return LANGUAGE_ALIASES.get(value, value)


def _runtime_for(language: str, runtimes: list[dict[str, Any]]) -> dict[str, Any] | None:
    target = normalize_language(language)
    for runtime in runtimes:
        names = {str(runtime.get("language", "")).lower()}
        names.update(str(alias).lower() for alias in runtime.get("aliases", []) if alias)
        if target in names:
            return runtime
    return None


async def execute_code(
    *,
    language: str,
    code: str,
    stdin: str = "",
    filename: str | None = None,
    extra_files: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_language(language)
    if normalized in SUPPORTED_STATIC:
        return _validate_markup(normalized, code)

    if not code or len(code.encode("utf-8")) > 200_000:
        raise CodeExecutionError("Code is empty or exceeds the 200 KB execution limit")

    runtimes = await list_runtimes()
    runtime = _runtime_for(normalized, runtimes)
    if runtime is None:
        raise CodeExecutionError(
            f"No runtime is installed for {normalized}. Install it in the AGENTX Piston runner."
        )

    default_names = {
        "python": "main.py",
        "javascript": "main.js",
        "typescript": "main.ts",
        "java": "Main.java",
        "c": "main.c",
        "c++": "main.cpp",
        "go": "main.go",
        "rust": "main.rs",
        "php": "main.php",
        "ruby": "main.rb",
        "bash": "main.sh",
    }
    files = [{"name": filename or default_names.get(normalized, "main.txt"), "content": code}]
    if extra_files:
        files.extend(extra_files)

    payload = {
        "language": runtime["language"],
        "version": runtime["version"],
        "files": files,
        "stdin": stdin[:20_000],
        "args": [],
        "compile_timeout": 10_000,
        "run_timeout": 5_000,
        "compile_memory_limit": 128 * 1024 * 1024,
        "run_memory_limit": 128 * 1024 * 1024,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(f"{settings.piston_url}/api/v2/execute", json=payload)
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as exc:
        raise CodeExecutionError(f"Code runner unavailable: {exc}") from exc

    compile_result = result.get("compile") or {}
    run_result = result.get("run") or {}
    return {
        "language": result.get("language", normalized),
        "version": result.get("version", runtime["version"]),
        "compile": compile_result,
        "run": run_result,
        "stdout": run_result.get("stdout", ""),
        "stderr": run_result.get("stderr", ""),
        "output": run_result.get("output", ""),
        "exit_code": run_result.get("code"),
        "signal": run_result.get("signal"),
        "success": run_result.get("code") == 0 and not compile_result.get("code"),
    }


def _validate_markup(language: str, code: str) -> dict[str, Any]:
    errors: list[str] = []
    if language == "html":
        lowered = code.lower()
        if "<html" not in lowered and "<!doctype" not in lowered:
            errors.append("HTML document does not contain an <html> or <!doctype> root")
        if "<body" not in lowered:
            errors.append("HTML document does not contain a <body> element")
    else:
        if "{" not in code or "}" not in code:
            errors.append("CSS appears to contain no complete rule block")
        if code.count("{") != code.count("}"):
            errors.append("CSS braces are unbalanced")
    return {
        "language": language,
        "version": "static-validator",
        "compile": {},
        "run": {},
        "stdout": "",
        "stderr": "\n".join(errors),
        "output": "\n".join(errors) if errors else f"{language.upper()} validation passed",
        "exit_code": 1 if errors else 0,
        "signal": None,
        "success": not errors,
    }
