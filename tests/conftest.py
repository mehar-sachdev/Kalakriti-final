from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.config import Settings, reset_settings_cache
from backend.logging_config import _SECRETS

_ENV_TO_CLEAR = [k for k in os.environ if k.split("_")[0] in {
    "SUPABASE", "OLLAMA", "EMBEDDING", "CHUNK", "TOP", "SIMILARITY", "RERANK", "OFFPEAK", "APP", "ENABLE", "LLM",
    "RAW", "PROCESSED", "REPORTS", "DOCLING", "PROMOTE", "API", "CORS", "LOG", "DB", "VECTOR", "DOCUMENTS",
    "AUTO", "MAX", "QUERY", "MIN"}]


# Real values, captured before isolation, for the opt-in integration tests only.
ORIGINAL_ENV = dict(os.environ)


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch):
    """Tests never read a developer's real .env or exported credentials."""
    for key in _ENV_TO_CLEAR:
        monkeypatch.delenv(key, raising=False)
    reset_settings_cache()
    yield
    _SECRETS.clear()
    reset_settings_cache()


@pytest.fixture
def make_settings(tmp_path):
    def factory(**overrides) -> Settings:
        base = dict(
            raw_dir=tmp_path / "raw", processed_dir=tmp_path / "processed", reports_dir=tmp_path / "reports",
            log_dir=tmp_path / "logs", frontend_dir=tmp_path / "frontend", embedding_provider="hash",
            enable_parser_fallback=True,
        )
        base.update(overrides)
        return Settings(_env_file=None, **base)
    return factory


@pytest.fixture
def settings(make_settings):
    return make_settings()


@pytest.fixture
def corpus(tmp_path):
    from tests.helpers import build_corpus

    return build_corpus(tmp_path / "raw")


@pytest.fixture
def offline_registry(settings, monkeypatch):
    """Parser registry that never asks Docling to run its PDF layout models (needs a big
    download): PDFs go straight to the pdfium fallback.  DOCX/XLSX use the real Docling."""
    from backend.exceptions import ParsingError
    from backend.ingestion.parser import DoclingParser, ParserRegistry

    original = DoclingParser.parse

    def parse(self, source):
        if source.file_type == "pdf":
            raise ParsingError("PDF layout models disabled in unit tests")
        return original(self, source)

    monkeypatch.setattr(DoclingParser, "parse", parse)
    return ParserRegistry(settings)
