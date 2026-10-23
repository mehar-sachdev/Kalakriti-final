"""Ollama Cloud LLM access.

* Auth: ``Authorization: Bearer <OLLAMA_API_KEY>`` against ``https://ollama.com``.
* Free plan = one concurrent cloud request -> a process-wide semaphore serialises calls.
* 429 / 5xx / connection errors are retried with exponential backoff; auth and
  model-not-found errors fail fast with an actionable hint.
* Errors are converted to secret-free :class:`LLMError` subclasses.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

import httpx
from llama_index.core.base.llms.types import ChatMessage, MessageRole

from backend.config import Settings
from backend.exceptions import ConfigurationError, LLMError, LLMTimeout
from backend.logging_config import redact

logger = logging.getLogger(__name__)


def build_llm(settings: Settings):
    try:
        from llama_index.llms.ollama import Ollama
    except ImportError as exc:
        raise ConfigurationError(
            "The LlamaIndex Ollama integration is not installed.", hint="pip install llama-index-llms-ollama"
        ) from exc
    settings.require("query")
    headers = None
    if settings.ollama_api_key is not None:
        headers = {"Authorization": f"Bearer {settings.ollama_api_key.get_secret_value()}"}
    kwargs: dict[str, Any] = dict(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url.rstrip("/"),
        request_timeout=settings.ollama_timeout_seconds,
        temperature=settings.ollama_temperature,
        headers=headers,
    )
    think = settings.ollama_think_value
    if think is not None:
        kwargs["thinking"] = think
    return Ollama(**kwargs)


def check_ollama(settings: Settings, timeout: float = 8.0) -> tuple[str, str | None]:
    """Lightweight availability check via GET /api/tags (does not consume model quota)."""
    if settings.uses_ollama_cloud and settings.ollama_api_key is None:
        return "not_configured", "OLLAMA_API_KEY is not set."
    headers = {}
    if settings.ollama_api_key is not None:
        headers["Authorization"] = f"Bearer {settings.ollama_api_key.get_secret_value()}"
    try:
        response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", headers=headers, timeout=timeout)
    except httpx.TimeoutException:
        return "error", "Timed out contacting Ollama."
    except httpx.HTTPError as exc:
        return "error", redact(f"Cannot reach Ollama: {type(exc).__name__}")
    if response.status_code in (401, 403):
        return "error", "Ollama rejected the API key (401/403)."
    if response.status_code >= 400:
        return "error", f"Ollama returned HTTP {response.status_code}."
    try:
        names = {m.get("name") or m.get("model") for m in response.json().get("models", [])}
    except ValueError:
        return "error", "Unexpected response from Ollama."
    wanted = settings.ollama_model
    if wanted in names or f"{wanted}:latest" in names:
        return "ok", None
    return "error", f"Model '{wanted}' is not in the list Ollama offers; pick one from {settings.ollama_base_url}/api/tags."


class LLMGateway:
    """Serialised, retrying chat completion."""

    _semaphores: dict[int, threading.BoundedSemaphore] = {}
    _lock = threading.Lock()

    def __init__(self, settings: Settings, llm=None):
        self.settings = settings
        self._llm = llm
        with self._lock:
            self._sem = self._semaphores.setdefault(
                settings.llm_max_concurrency, threading.BoundedSemaphore(settings.llm_max_concurrency)
            )

    @property
    def llm(self):
        if self._llm is None:
            self._llm = build_llm(self.settings)
        return self._llm

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=user_prompt),
        ]
        attempts = self.settings.llm_max_retries + 1
        last_error: Exception | None = None
        with self._sem:
            for attempt in range(1, attempts + 1):
                try:
                    response = self.llm.chat(messages)
                    content = (response.message.content or "").strip()
                    if not content:
                        raise LLMError(
                            "The model returned an empty answer.",
                            hint="Reasoning models can spend the whole budget thinking; try OLLAMA_THINK=low or another model.",
                        )
                    return content
                except LLMError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    retryable, error = self._classify(exc)
                    if not retryable or attempt == attempts or (isinstance(error, LLMTimeout) and attempt >= 2):
                        raise error from exc
                    delay = min(2 ** (attempt - 1), 20) + random.uniform(0, 0.5)
                    logger.warning("LLM call failed (%s); retry %d/%d in %.1fs", type(exc).__name__, attempt, attempts - 1, delay)
                    time.sleep(delay)
        raise LLMError(redact(str(last_error)))  # pragma: no cover

    def _classify(self, exc: Exception) -> tuple[bool, LLMError]:
        status = getattr(exc, "status_code", None)
        name = type(exc).__name__
        if isinstance(exc, (httpx.TimeoutException,)) or "Timeout" in name:
            return True, LLMTimeout(
                f"The model did not answer within {self.settings.ollama_timeout_seconds:.0f}s.",
                hint="Ollama Cloud may be busy - retry later (off-peak) or raise OLLAMA_TIMEOUT_SECONDS.",
            )
        if status in (401, 403):
            return False, LLMError("Ollama rejected the API key.", hint="Create a new key at https://ollama.com/settings/keys and update OLLAMA_API_KEY.")
        if status == 404:
            return False, LLMError(
                f"Model '{self.settings.ollama_model}' was not found.",
                hint="List valid names with: curl https://ollama.com/api/tags  and set OLLAMA_MODEL.",
            )
        if status == 429:
            return True, LLMError(
                "Ollama Cloud usage limit reached (HTTP 429).",
                hint="The free plan has session/weekly limits and one concurrent request. Wait and retry, ideally off-peak.",
            )
        if status is not None and status >= 500:
            return True, LLMError(f"Ollama Cloud is temporarily unavailable (HTTP {status}).", hint="Retry shortly or switch OLLAMA_MODEL.")
        if isinstance(exc, (httpx.ConnectError, ConnectionError)) or "Connect" in name:
            return True, LLMError("Cannot connect to Ollama.", hint="Check your internet connection and OLLAMA_BASE_URL.")
        return False, LLMError(redact(f"{name}: {exc}")[:300])
