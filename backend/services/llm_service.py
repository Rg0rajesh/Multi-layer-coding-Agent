from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)


class OllamaUnavailableError(Exception):
    """Connection-level failure that can be retried by the worker."""


class LLMGenerationError(Exception):
    """Ollama responded, but the response could not be used."""

    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


_client: httpx.AsyncClient | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.ollama_url,
            timeout=httpx.Timeout(
                connect=5.0,
                read=settings.ollama_timeout_seconds,
                write=10.0,
                pool=5.0,
            ),
        )
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.ollama_max_concurrent_requests)
    return _semaphore


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


_MAX_CONNECTION_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 1.5
_MAX_JSON_ATTEMPTS = 2


async def chat(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> str:
    """Send one request to Ollama and return the assistant text."""
    payload: dict[str, Any] = {
        "model": model or settings.ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 1200 if json_mode else 400,
        },
    }

    if json_mode:
        payload["format"] = "json"

    client = _get_client()
    last_error: Exception | None = None

    for attempt in range(1, _MAX_CONNECTION_RETRIES + 1):
        try:
            async with _get_semaphore():
                response = await client.post("/api/chat", json=payload)

            response.raise_for_status()
            body = response.json()
            content = body.get("message", {}).get("content", "")

            if not content:
                choices = body.get("choices", [])
                if isinstance(choices, list) and choices:
                    first_choice = choices[0]
                    if isinstance(first_choice, dict):
                        content = (
                            first_choice.get("message", {}).get("content", "")
                            or first_choice.get("text", "")
                        )

            if not content:
                raise LLMGenerationError(
                    "Ollama returned an empty response",
                    raw_response=str(body),
                )

            return content

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt < _MAX_CONNECTION_RETRIES:
                logger.warning(
                    "Ollama unreachable (attempt %d/%d), retrying: %s",
                    attempt,
                    _MAX_CONNECTION_RETRIES,
                    exc,
                )
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
                continue

            raise OllamaUnavailableError(
                f"Ollama unreachable after {attempt} attempts"
            ) from exc

        except httpx.HTTPStatusError as exc:
            raise LLMGenerationError(
                f"Ollama returned {exc.response.status_code}: "
                f"{exc.response.text[:300]}"
            ) from exc

    raise OllamaUnavailableError(str(last_error))


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from normal JSON or fenced/model-prefixed text."""
    candidate = text.strip().lstrip("\ufeff")

    fence_match = _JSON_FENCE_RE.search(candidate)
    if fence_match:
        candidate = fence_match.group(1).strip()

    try:
        value = json.loads(candidate)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            value = json.loads(candidate[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

    raise LLMGenerationError(
        "Model output wasn't valid JSON",
        raw_response=text,
    )


async def generate_json(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Generate a JSON object with one automatic correction attempt.

    Qwen 3B occasionally ignores the requested structure even when Ollama's
    JSON mode is enabled. The second request explicitly reminds the model that
    the response must be one complete JSON object. This is a generation retry,
    not a connection retry.
    """
    last_error: LLMGenerationError | None = None
    current_user = user

    for attempt in range(1, _MAX_JSON_ATTEMPTS + 1):
        try:
            raw = await chat(
                system=system,
                user=current_user,
                model=model,
                temperature=0.0 if attempt > 1 else temperature,
                json_mode=True,
            )
            return _extract_json(raw)
        except LLMGenerationError as exc:
            last_error = exc
            logger.warning(
                "Invalid JSON from model (attempt %d/%d): %s",
                attempt,
                _MAX_JSON_ATTEMPTS,
                exc,
            )
            if attempt < _MAX_JSON_ATTEMPTS:
                current_user = (
                    f"{user}\n\n"
                    "IMPORTANT CORRECTION: Your previous response was unusable. "
                    "Return ONLY ONE complete valid JSON OBJECT. No markdown, no "
                    "explanation, no code fence, and no text before or after the JSON."
                )

    assert last_error is not None
    raise last_error


async def classify_risk(
    task_description: str,
    prior_score: float = 0.0,
) -> dict[str, Any]:
    """Classify an incoming task with the configured Llama Guard model."""
    system = (
        "You are a safety classifier. "
        "Classify the user's request as exactly one of: safe or unsafe. "
        "Output only one word: safe or unsafe."
    )

    raw = await chat(
        system=system,
        user=task_description,
        model=settings.llama_guard_model,
        temperature=0.0,
    )

    result = raw.strip().lower()

    if result.startswith("safe"):
        return {
            "risk_score": 0,
            "reason": "Llama Guard classified the request as safe",
        }

    if result.startswith("unsafe"):
        return {
            "risk_score": 100,
            "reason": "Llama Guard classified the request as unsafe",
        }

    raise LLMGenerationError(
        "Llama Guard returned an unexpected classification",
        raw_response=raw,
    )


async def ensure_model_ready(model: str) -> None:
    """Warm the requested model when it is not already listed by Ollama."""
    try:
        client = _get_client()
        response = await client.get("/api/tags")
        response.raise_for_status()
        loaded = {m["name"] for m in response.json().get("models", [])}
        if model not in loaded:
            logger.info("Warming up %s — first call after this will be slow", model)
            await chat(
                system="You are a helper.",
                user="ready?",
                model=model,
                temperature=0.0,
            )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.warning("Couldn't warm up %s: %s", model, exc)
