"""FastAPI application.

    uvicorn backend.main:app --reload           (development)
    python -m backend.main                      (uses API_HOST / API_PORT)

One process serves the storefront (``frontend/index.html``, images) *and* the API on the same
origin - open http://127.0.0.1:8000/ and everything (products, orders, the AI chat) works with no
separate dev server and no CORS to configure. CORS is still available (CORS_ORIGINS) for anyone
who wants to host the frontend separately.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend import __version__
from backend.api.errors import register_error_handlers
from backend.api.routes import protected, public
from backend.api.state import AppState
from backend.config import Settings, get_settings
from backend.logging_config import setup_logging
from backend.rag.catalog import Catalog
from backend.rag.engine import RAGEngine
from backend.services.catalog_service import CatalogService

logger = logging.getLogger("backend.main")


def create_app(
    settings: Settings | None = None, *, engine: RAGEngine | None = None, catalog: Catalog | None = None,
    shop: CatalogService | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level, settings.log_format, settings.log_dir)

    app = FastAPI(
        title="Kalakriti AI - Handicraft Storefront + RAG Assistant",
        version=__version__,
        description="Real LlamaIndex RAG (Docling + BAAI/bge-small-en-v1.5 + Supabase pgvector + Ollama Cloud) "
                    "integrated into the Kalakriti handicraft storefront.",
    )
    app.state.rag = AppState(
        settings=settings, engine=engine or RAGEngine(settings), catalog=catalog or Catalog(settings),
        shop=shop or CatalogService(settings),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_allow_origin_regex or None,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
        max_age=600,
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        if not request.url.path.startswith(("/images", "/favicon")):
            logger.info("%s %s -> %d (%d ms)", request.method, request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    register_error_handlers(app)
    app.include_router(public)     # registered first: takes priority over the "/" static catch-all below
    app.include_router(protected)

    frontend = Path(settings.frontend_dir)
    if (frontend / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    s = get_settings()
    uvicorn.run("backend.main:app", host=s.api_host, port=s.api_port, reload=False)
