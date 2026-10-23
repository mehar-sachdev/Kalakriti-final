#!/usr/bin/env python
"""Smoke-test the RAG pipeline end to end: config, database, retrieval, and one real chat
question if credentials are configured. Prints PASS/FAIL per check; does not fabricate results
for checks it cannot run.

    python scripts/test_rag.py
"""
import sys

import _bootstrap  # noqa: F401
from backend.config import get_settings
from backend.exceptions import RAGError
from backend.logging_config import redact, setup_logging


def check(label):
    def decorator(fn):
        try:
            detail = fn()
            print(f"[ OK ] {label}" + (f" - {detail}" if detail else ""))
            return True
        except RAGError as exc:
            print(f"[FAIL] {label} - {redact(exc.message)}" + (f" ({exc.hint})" if exc.hint else ""))
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {label} - {type(exc).__name__}: {redact(str(exc))[:200]}")
        return False
    return decorator


def main() -> int:
    settings = get_settings()
    setup_logging("WARNING")
    results = []

    @check("Configuration (.env)")
    def _cfg():
        missing = settings.missing_for("query")
        if missing:
            raise RAGError("Missing: " + ", ".join(n for n, _ in missing))
        return "SUPABASE_DB_URL and OLLAMA_API_KEY are set"
    results.append(_cfg)

    @check("Product catalogue (data/metadata/products.json)")
    def _catalog():
        from backend.rag import products as pc
        n = len(pc.load_catalog())
        if n != 146:
            raise RAGError(f"expected 146 products, found {n}")
        return f"{n} products loaded"
    results.append(_catalog)

    @check("Structured product filtering")
    def _filter():
        from backend.rag import products as pc
        under = pc.filter_products(max_price=3000)
        diff = pc.largest_price_difference(1)
        if not under or not diff:
            raise RAGError("filter/comparison returned no results")
        return f"{len(under)} products under Rs.3000; largest diff: {diff[0]['name']}"
    results.append(_filter)

    if not settings.missing_for("index"):
        @check("Database connectivity (Supabase pgvector)")
        def _db():
            from backend.database.connection import check_database
            status, detail = check_database(settings)
            if status != "ok":
                raise RAGError(detail or status)
            return "connected"
        results.append(_db)

    if not settings.missing_for("query"):
        @check("Retrieval + chat (real question)")
        def _rag():
            from backend.models.schemas import QueryRequest
            from backend.rag.engine import RAGEngine
            response = RAGEngine(settings).query(QueryRequest(question="Tell me about the Banarasi Silk Dupatta"))
            if not response.products and not response.sources:
                raise RAGError("no products or sources returned - is the index built? run scripts/ingest.py")
            return f"{len(response.products)} product(s), {len(response.sources)} source(s)"
        results.append(_rag)

    print()
    if all(results):
        print("All checks passed.")
        return 0
    print("Some checks failed or were skipped (see above). This does not always mean the app is broken -")
    print("checks needing Supabase/Ollama are skipped until SUPABASE_DB_URL/OLLAMA_API_KEY are set in .env.")
    return 1 if not all(results) else 0


if __name__ == "__main__":
    sys.exit(main())
