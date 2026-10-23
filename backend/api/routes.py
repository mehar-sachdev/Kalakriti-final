"""HTTP endpoints.

Two routers:
* ``public``    - the storefront itself calls these with no key: /health, /products, /orders,
  /api/chat, /api/categories, /api/documents, /api/stats (an academic demo has nothing
  confidential to hide behind a key; only administrative actions are gated).
* ``protected`` - background ingestion, gated by APP_API_KEY and off by default.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import JSONResponse

from backend import __version__
from backend.api.state import AppState, get_state, rate_limit, require_api_key
from backend.database.connection import check_database
from backend.exceptions import FeatureDisabled, InvalidRequest, RAGError
from backend.models.schemas import (
    ComponentStatus,
    DepartmentInfo,
    DocumentInfo,
    HealthResponse,
    IngestJob,
    IngestRequest,
    OrderRequest,
    QueryRequest,
    QueryResponse,
    SourceDetail,
    StatsResponse,
)
from backend.rag.llm import check_ollama
from backend.rag import products as product_catalog

logger = logging.getLogger(__name__)
public = APIRouter()
protected = APIRouter(dependencies=[Depends(require_api_key)])

_HEALTH_TTL = 30.0


# ---------------------------------------------------------------------------- health
@public.get("/health", response_model=HealthResponse, tags=["system"])
def health(state: AppState = Depends(get_state)) -> HealthResponse:
    """Liveness + dependency status. Never returns secrets; cached for 30 s."""
    now = time.monotonic()
    if state.health_cache and now - state.health_cache[0] < _HEALTH_TTL:
        return state.health_cache[1]
    s = state.settings

    components: dict[str, ComponentStatus] = {"api": ComponentStatus(status="ok")}
    missing = s.missing_for("query")
    components["config"] = ComponentStatus(
        status="ok" if not missing else "not_configured",
        detail=None if not missing else "Missing: " + ", ".join(name for name, _ in missing),
    )
    db_status, db_detail = check_database(s)
    components["rag_database"] = ComponentStatus(status=db_status, detail=db_detail)
    llm_status, llm_detail = check_ollama(s)
    components["llm"] = ComponentStatus(status=llm_status, detail=llm_detail)
    shop_status, shop_detail = state.shop.health()
    components["storefront_data"] = ComponentStatus(status=shop_status, detail=shop_detail)
    try:
        components["embeddings"] = ComponentStatus(status="ok", detail=s.embedding_signature)
    except RAGError as exc:
        components["embeddings"] = ComponentStatus(status="error", detail=exc.message)

    # The storefront (products/orders) is expected to work even before Supabase/Ollama are set up
    # (local catalog fallback); only treat the app as unhealthy if the API itself is broken.
    healthy = components["api"].status == "ok"
    result = HealthResponse(
        status="ok" if healthy else "degraded", version=__version__, components=components,
        off_peak=s.is_off_peak(), off_peak_enabled=s.offpeak_enabled,
        embedding=s.embedding_model, llm_model=s.ollama_model,
    )
    state.health_cache = (now, result)
    return result


# ---------------------------------------------------------------------------- storefront (legacy, preserved)
@public.get("/products", tags=["storefront"])
def list_products(state: AppState = Depends(get_state)) -> list[dict]:
    """Unchanged response shape from the original storefront backend (product_id, product_name,
    region, craft, material, technique, origin, artisan_id, price, rating, image_url,
    description, stock_quantity, status) - reads from Supabase when configured, otherwise from
    the local product catalog so the site works without any setup."""
    return state.shop.list_products()


@public.get("/api/regions", tags=["storefront"])
def regions() -> list[dict]:
    """Generated catalogue hierarchy used by the storefront's city and craft filters."""
    return product_catalog.load_hierarchy()


@public.post("/orders", tags=["storefront"])
def create_order(order: OrderRequest, state: AppState = Depends(get_state)) -> dict:
    """Unchanged from the original storefront backend. Requires a configured Supabase project -
    a local JSON catalog has no stock ledger to safely decrement."""
    return state.shop.create_order(order.model_dump())


# ---------------------------------------------------------------------------- chat (new: the RAG assistant)
@public.post("/api/chat", response_model=QueryResponse, tags=["chat"], dependencies=[Depends(rate_limit)])
def chat(request: QueryRequest, state: AppState = Depends(get_state)) -> QueryResponse:
    """Ask the Kalakriti AI assistant a question. Answer is grounded in the product/regional/
    craft/competitor documents; ``products`` carries structured cards for the frontend to render,
    ``sources`` the cited excerpts."""
    limit = state.settings.max_question_chars
    if len(request.question) > limit:
        raise InvalidRequest(f"Question is too long ({len(request.question)} > {limit} characters).", hint="Shorten the question.")
    state.settings.require("query")
    logger.info("Chat question received (%d chars)", len(request.question))
    return state.engine.query(request)


@public.post("/query", response_model=QueryResponse, tags=["chat"], include_in_schema=False, dependencies=[Depends(rate_limit)])
def query_alias(request: QueryRequest, state: AppState = Depends(get_state)) -> QueryResponse:
    """Alias of /api/chat kept for scripts/query_cli.py and the evaluation harness."""
    return chat(request, state)


# ---------------------------------------------------------------------------- RAG catalog (categories/documents/sources)
@public.get("/api/categories", response_model=list[DepartmentInfo], tags=["catalog"])
def categories(state: AppState = Depends(get_state)) -> list[DepartmentInfo]:
    """Document categories discovered from documents/ (product, competitor, regional, craft, artisan)."""
    return state.catalog.departments()


@public.get("/api/documents", response_model=list[DocumentInfo], tags=["catalog"])
def documents(
    category: Optional[str] = Query(None, description="Document category: product, competitor, regional, craft or artisan"),
    document_type: Optional[str] = Query(None),
    state: AppState = Depends(get_state),
) -> list[DocumentInfo]:
    return state.catalog.documents(category, document_type)


@public.get("/api/stats", response_model=StatsResponse, tags=["catalog"])
def stats(state: AppState = Depends(get_state)) -> StatsResponse:
    return state.catalog.stats()


@public.get("/api/sources/{document_id}", response_model=SourceDetail, tags=["catalog"])
def source_detail(
    document_id: str, include_markdown: bool = Query(False), state: AppState = Depends(get_state)
) -> SourceDetail:
    """Metadata (and optionally the converted Markdown) of one source document."""
    return state.catalog.source_detail(document_id, include_markdown)


# ---------------------------------------------------------------------------- ingestion (opt-in, admin)
def _run_job(state: AppState, job_id: str, department: Optional[str], force: bool) -> None:
    from backend.ingest import run_index, run_parse

    job = state.jobs[job_id]
    job["status"] = "running"
    try:
        parsed = run_parse(state.settings, department=department, force=force)
        indexed = run_index(state.settings, department=department, force=force)
        job.update(status="done", summary={
            "parsed": parsed.count("success"), "parse_failed": parsed.count("failed"), "unchanged": parsed.count("skipped"),
            **{f"index_{k}": v for k, v in indexed.to_dict().items() if k != "errors"},
        })
    except RAGError as exc:
        job.update(status="failed", detail=f"{exc.message} {exc.hint or ''}".strip())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ingestion job failed")
        job.update(status="failed", detail=f"{type(exc).__name__} (see server log)")
    finally:
        state.job_lock.release()
        state.catalog._registry = None  # force a fresh look at the registry


@protected.post("/api/ingest", response_model=IngestJob, status_code=202, tags=["admin"])
def ingest(body: IngestRequest, background: BackgroundTasks, state: AppState = Depends(get_state)):
    """Parse + index the documents in the background. Disabled unless ENABLE_INGEST_API=true."""
    if not state.settings.enable_ingest_api:
        raise FeatureDisabled(
            "Ingestion through the API is disabled.", hint="Run `python -m backend.ingest all`, or set ENABLE_INGEST_API=true (use APP_API_KEY too)."
        )
    if not state.job_lock.acquire(blocking=False):
        return JSONResponse(
            {"error": {"code": "ingest_running", "message": "An ingestion job is already running.", "hint": None}}, status_code=409
        )
    job_id = uuid.uuid4().hex[:12]
    state.jobs[job_id] = {"job_id": job_id, "status": "queued", "detail": None, "summary": {}}
    background.add_task(_run_job, state, job_id, body.department, body.force)
    return IngestJob(**state.jobs[job_id])


@protected.get("/api/ingest/{job_id}", response_model=IngestJob, tags=["admin"])
def ingest_status(job_id: str, state: AppState = Depends(get_state)) -> IngestJob:
    job = state.jobs.get(job_id)
    if job is None:
        from backend.exceptions import NotFoundError

        raise NotFoundError(f"No ingestion job '{job_id}'.")
    return IngestJob(**job)
