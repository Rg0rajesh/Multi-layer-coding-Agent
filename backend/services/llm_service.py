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


async def ensure_model_ready(model: str) -> None:
    """Check that Ollama is reachable and the requested model is available.

    This is intentionally a lightweight startup check. It does not generate
    tokens or pull a model automatically, so application startup remains fast
    and predictable. A failure is raised for the lifespan handler to log; the
    normal request path will retry Ollama when it is actually needed.
    """
    client = _get_client()
    try:
        response = await client.post("/api/show", json={"name": model})
        if response.status_code == 404:
            raise OllamaUnavailableError(
                f"Ollama model '{model}' is not installed. Pull it with: ollama pull {model}"
            )
        response.raise_for_status()
        logger.info("Ollama model ready: %s", model)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise OllamaUnavailableError(f"Ollama is unreachable at {settings.ollama_url}") from exc
    except httpx.HTTPStatusError as exc:
        raise OllamaUnavailableError(
            f"Ollama model check failed for '{model}': HTTP {exc.response.status_code}"
        ) from exc


_MAX_CONNECTION_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 1.5
_MAX_JSON_ATTEMPTS = 3


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
            "num_predict": 5000 if json_mode else 800,
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
                raise LLMGenerationError("Ollama returned an empty response", raw_response=str(body))

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

            raise OllamaUnavailableError(f"Ollama unreachable after {attempt} attempts") from exc

        except httpx.HTTPStatusError as exc:
            raise LLMGenerationError(
                f"Ollama returned {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc

    raise OllamaUnavailableError(str(last_error))


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract one JSON object from normal, fenced, or prefixed model output."""
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

    decoder = json.JSONDecoder()
    start = candidate.find("{")
    if start != -1:
        try:
            value, _ = decoder.raw_decode(candidate[start:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

    raise LLMGenerationError("Model output wasn't valid JSON", raw_response=text)


async def generate_json(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Generate a JSON object with automatic correction attempts."""
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
                "Invalid JSON from model (attempt %d/%d): %s; raw=%r",
                attempt,
                _MAX_JSON_ATTEMPTS,
                exc,
                exc.raw_response[:1000],
            )
            if attempt < _MAX_JSON_ATTEMPTS:
                current_user = (
                    f"{user}\n\nIMPORTANT CORRECTION: The previous response was unusable. "
                    "Return ONLY ONE complete JSON OBJECT. Do not use markdown, code fences, "
                    "explanations, comments outside JSON, or extra text. The JSON must start "
                    "with { and end with }. Preserve every required field and include complete source-code strings."
                )

    assert last_error is not None
    raise last_error


_DEV_INTENT = re.compile(
    r"\b(build|create|implement|develop|add|fix|refactor|update|test|debug|write|modify)\b"
    r".*\b(app|application|frontend|backend|component|page|api|calculator|website|feature|test|code|ui|typescript|javascript|python|react)\b",
    re.IGNORECASE | re.DOTALL,
)
_HIGH_RISK = re.compile(
    r"\b(malware|ransomware|keylogger|credential\s*steal|password\s*steal|token\s*steal|"
    r"exfiltrat(?:e|ion)|botnet|payload\s+delivery|persistence\s+mechanism|reverse\s+shell|"
    r"bypass\s+(?:authentication|security|detection|antivirus)|disable\s+(?:security|antivirus)|"
    r"destructive\s+command|delete\s+all\s+files|wipe\s+disk)\b",
    re.IGNORECASE,
)


def _is_unambiguously_benign_dev_task(task_description: str) -> bool:
    text = " ".join(task_description.split())
    return bool(_DEV_INTENT.search(text)) and not bool(_HIGH_RISK.search(text))


async def classify_risk(
    task_description: str,
    prior_score: float = 0.0,
) -> dict[str, Any]:
    """Classify an incoming task without letting benign coding false positives
    poison the rolling session score.

    The deterministic check is intentionally narrow: it recognizes ordinary
    application-development requests only when no high-risk intent is present.
    All other requests still go through Llama Guard. Authorization is handled
    separately by the Identity Broker/OPA layer.
    """
    if _is_unambiguously_benign_dev_task(task_description):
        return {
            "risk_score": 0,
            "reason": "Ordinary application-development request with no high-risk indicators",
        }

    system = (
        "You are a safety classifier for a software-development agent. "
        "Classify the user's request as exactly one of: safe or unsafe. "
        "Ordinary programming, frontend/backend development, debugging, testing, "
        "UI work, calculators, parsers, localStorage, databases, APIs, and normal "
        "software engineering are safe. Only classify unsafe when the request "
        "meaningfully facilitates harmful activity such as malware, credential theft, "
        "data exfiltration, destructive actions, unauthorized access, or security bypass. "
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
        return {"risk_score": 0, "reason": "Llama Guard classified the request as safe"}

    if result.startswith("unsafe"):
        return {"risk_score": 100, "reason": "Llama Guard classified the request as unsafe"}

    raise LLMGenerationError(
        "Llama Guard returned an unexpected classification",
        raw_response=raw,
    )
