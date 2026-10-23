"""Application state, auth and rate-limit dependencies."""
from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, Header, Request

from backend.config import Settings
from backend.exceptions import RAGError
from backend.rag.catalog import Catalog
from backend.rag.engine import RAGEngine
from backend.services.catalog_service import CatalogService


class Unauthorized(RAGError):
    code = "unauthorized"
    http_status = 401


class TooManyRequests(RAGError):
    code = "rate_limited"
    http_status = 429


@dataclass
class AppState:
    settings: Settings
    engine: RAGEngine
    catalog: Catalog
    shop: CatalogService
    health_cache: tuple[float, Any] | None = None
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    job_lock: threading.Lock = field(default_factory=threading.Lock)
    hits: dict[str, deque] = field(default_factory=lambda: defaultdict(deque))


def get_state(request: Request) -> AppState:
    return request.app.state.rag


def require_api_key(state: AppState = Depends(get_state), x_api_key: str | None = Header(default=None)) -> None:
    key = state.settings.app_api_key
    if key is None:
        return
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), key.get_secret_value().encode()):
        raise Unauthorized("A valid X-API-Key header is required.", hint="Ask the administrator for the access key.")


def rate_limit(request: Request, state: AppState = Depends(get_state)) -> None:
    limit = state.settings.query_rate_limit_per_minute
    if limit <= 0:
        return
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = state.hits[client]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise TooManyRequests(
            f"Rate limit reached ({limit} questions per minute).",
            hint="Wait a moment before asking again; this protects the shared Ollama Cloud quota.",
        )
    window.append(now)
