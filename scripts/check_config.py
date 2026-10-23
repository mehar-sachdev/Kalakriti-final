#!/usr/bin/env python
"""Verify .env, Supabase and Ollama Cloud connectivity without printing any secret."""
import sys

import _bootstrap  # noqa: F401
from backend.config import PROJECT_ROOT, get_settings
from backend.database.connection import check_database
from backend.exceptions import RAGError
from backend.logging_config import setup_logging
from backend.rag.llm import check_ollama


def line(label: str, status: str, detail: str | None = None) -> None:
    mark = {"ok": "OK  ", "not_configured": "TODO", "error": "FAIL"}.get(status, status)
    print(f"[{mark}] {label}" + (f" - {detail}" if detail else ""))


def main() -> int:
    settings = get_settings()
    setup_logging("WARNING")
    print(f".env file : {'found' if (PROJECT_ROOT / '.env').exists() else 'MISSING (copy .env.example to .env)'}")
    for name, hint in settings.missing_for("query"):
        line(name, "not_configured", hint)
    status, detail = check_database(settings)
    line("Supabase Postgres + pgvector", status, detail)
    status2, detail2 = check_ollama(settings)
    line(f"Ollama ({settings.ollama_base_url}, model {settings.ollama_model})", status2, detail2)
    try:
        line(f"Embeddings {settings.embedding_signature}", "ok", "model is downloaded on first use" if settings.embedding_provider == "huggingface" else None)
    except RAGError as exc:
        line("Embeddings", "error", exc.message)
    window = f"{settings.offpeak_start}-{settings.offpeak_end} {settings.offpeak_tz}"
    print(f"Off-peak  : {'enabled ' + window + ' (currently ' + ('inside' if settings.is_off_peak() else 'outside') + ', enforce=' + str(settings.offpeak_enforce) + ')' if settings.offpeak_enabled else 'disabled'}")
    return 0 if status == "ok" and status2 == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
