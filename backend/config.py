"""Centralised configuration.

All settings come from environment variables (optionally loaded from ``.env``).
Nothing secret is ever hard-coded; secrets are :class:`pydantic.SecretStr` so they
do not leak through ``repr`` or accidental logging.
"""
from __future__ import annotations

from datetime import datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.exceptions import ConfigurationError
from backend.logging_config import register_secret

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Embedding dimensionalities of models we know about.  Anything else needs an
# explicit EMBEDDING_DIM.
KNOWN_EMBEDDING_DIMS: dict[str, int] = {
    "baai/bge-small-en-v1.5": 384,
    "baai/bge-base-en-v1.5": 768,
    "baai/bge-large-en-v1.5": 1024,
    "sentence-transformers/all-minilm-l6-v2": 384,
    "intfloat/multilingual-e5-small": 384,
    "nomic-embed-text": 768,
    "bge-m3": 1024,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,  # so a field with a validation_alias (EMBEDDING_DIM/EMBEDDING_DIMENSION,
                                 # API_HOST/APP_HOST, API_PORT/APP_PORT) can still be set by its own
                                 # Python name too, e.g. Settings(embedding_dim=512) in tests and scripts -
                                 # this must not depend on which pydantic/pydantic-settings version resolves
                                 # keyword construction vs. alias matching.
    )

    # --- paths --------------------------------------------------------------
    raw_dir: Path = Path("documents")
    processed_dir: Path = Path("data/processed")
    reports_dir: Path = Path("reports")
    log_dir: Path = Path("logs")
    frontend_dir: Path = Path("frontend")

    # --- Supabase / Postgres -------------------------------------------------
    supabase_db_url: Optional[SecretStr] = None
    supabase_url: Optional[str] = None
    supabase_key: Optional[SecretStr] = None   # legacy storefront REST API (products/orders) - separate from the RAG store
    db_schema: str = "rag"
    vector_table: str = "kalakriti_chunks"
    documents_table: str = "documents"

    # --- Ollama Cloud ---------------------------------------------------------
    ollama_api_key: Optional[SecretStr] = None
    ollama_base_url: str = "https://ollama.com"
    ollama_model: str = "gpt-oss:20b"
    ollama_timeout_seconds: float = 120.0
    ollama_web_search_enabled: bool = True
    ollama_web_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    ollama_temperature: float = 0.1
    ollama_think: str = ""
    llm_max_concurrency: int = Field(default=1, ge=1)
    llm_max_retries: int = Field(default=3, ge=0)

    offpeak_enabled: bool = False
    offpeak_start: str = "22:00"
    offpeak_end: str = "07:00"
    offpeak_tz: str = "Asia/Kolkata"
    offpeak_enforce: bool = False

    # --- embeddings -------------------------------------------------------------
    embedding_provider: Literal["huggingface", "ollama", "hash"] = "huggingface"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = Field(default=0, validation_alias=AliasChoices("EMBEDDING_DIM", "EMBEDDING_DIMENSION"))
    embedding_batch_size: int = Field(default=32, ge=1)
    embedding_query_instruction: str = "Represent this sentence for searching relevant passages:"
    embedding_ollama_base_url: str = "http://localhost:11434"

    # --- chunking -----------------------------------------------------------------
    chunk_size: int = Field(default=400, ge=50)
    chunk_overlap: int = Field(default=60, ge=0)
    min_chunk_size: int = Field(default=40, ge=0)

    # --- retrieval ----------------------------------------------------------------
    top_k: int = Field(default=6, ge=1, le=50)
    similarity_cutoff: float = Field(default=0.25, ge=0.0, le=1.0)
    rerank_enabled: bool = False
    rerank_model: str = "BAAI/bge-reranker-base"
    rerank_candidates: int = Field(default=20, ge=1, le=200)
    max_context_chars: int = Field(default=12000, ge=1000)
    auto_department_detection: bool = True

    # --- ingestion -----------------------------------------------------------------
    docling_do_ocr: bool = False
    docling_table_structure: bool = True
    docling_document_timeout_seconds: float = 300.0
    promote_numbered_headings: bool = True
    enable_parser_fallback: bool = False

    # --- API -------------------------------------------------------------------------
    api_host: str = Field(default="127.0.0.1", validation_alias=AliasChoices("API_HOST", "APP_HOST"))
    api_port: int = Field(default=8000, validation_alias=AliasChoices("API_PORT", "APP_PORT"))
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    # ngrok's free tier mints a new random subdomain every time the tunnel restarts, so it can
    # never be put in the static CORS_ORIGINS list above. This regex matches any ngrok hostname
    # without hardcoding a specific URL; leave it blank to disable ngrok access entirely.
    cors_allow_origin_regex: str = r"^https://([a-z0-9-]+\.)*ngrok-free\.app$|^https://([a-z0-9-]+\.)*ngrok\.(io|app|dev)$"
    app_api_key: Optional[SecretStr] = None
    enable_ingest_api: bool = False
    max_question_chars: int = Field(default=1000, ge=50)
    query_rate_limit_per_minute: int = Field(default=20, ge=0)   # per client IP; 0 disables

    # --- logging -------------------------------------------------------------------------
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # ------------------------------------------------------------------ validators
    @field_validator("raw_dir", "processed_dir", "reports_dir", "log_dir", "frontend_dir", mode="after")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        return value if value.is_absolute() else (PROJECT_ROOT / value)

    @field_validator("supabase_db_url", "ollama_api_key", "app_api_key", "supabase_key", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_lt_size(cls, value: int, info):
        size = info.data.get("chunk_size", 400)
        if value >= size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return value

    # ------------------------------------------------------------------ derived
    @property
    def manifest_path(self) -> Path:
        return self.processed_dir / "manifest.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_embedding_dim(self) -> int:
        if self.embedding_dim > 0:
            return self.embedding_dim
        if self.embedding_provider == "hash":
            return 384
        dim = KNOWN_EMBEDDING_DIMS.get(self.embedding_model.lower())
        if dim is None:
            raise ConfigurationError(
                f"Unknown embedding dimensionality for model '{self.embedding_model}'.",
                hint="Set EMBEDDING_DIM in .env to the model's output size.",
            )
        return dim

    @property
    def embedding_signature(self) -> str:
        """Identifies the embedding space; vectors from different signatures must not be mixed."""
        return f"{self.embedding_provider}:{self.embedding_model}:{self.resolved_embedding_dim}"

    @property
    def ollama_think_value(self) -> bool | str | None:
        raw = self.ollama_think.strip().lower()
        if not raw:
            return None
        if raw in {"true", "1", "yes"}:
            return True
        if raw in {"false", "0", "no"}:
            return False
        if raw in {"low", "medium", "high"}:
            return raw
        raise ConfigurationError(
            f"OLLAMA_THINK='{self.ollama_think}' is invalid.", hint="Use low, medium, high, true, false or leave empty."
        )

    @property
    def uses_ollama_cloud(self) -> bool:
        return "ollama.com" in self.ollama_base_url

    # ------------------------------------------------------------------ checks
    def missing_for(self, stage: Literal["parse", "index", "query", "api"]) -> list[tuple[str, str]]:
        """Return ``(variable, how to fix)`` pairs that are required for ``stage`` but missing."""
        missing: list[tuple[str, str]] = []
        if stage in {"index", "query", "api"} and self.supabase_db_url is None:
            missing.append(
                ("SUPABASE_DB_URL", "Supabase > Project Settings > Database > Connection string (Session pooler).")
            )
        if stage in {"query"} and self.uses_ollama_cloud and self.ollama_api_key is None:
            missing.append(("OLLAMA_API_KEY", "Create one at https://ollama.com/settings/keys."))
        return missing

    def require(self, stage: Literal["parse", "index", "query", "api"]) -> None:
        missing = self.missing_for(stage)
        if missing:
            names = ", ".join(name for name, _ in missing)
            hints = " ".join(f"{name}: {hint}" for name, hint in missing)
            env_file = PROJECT_ROOT / ".env"
            prefix = "" if env_file.exists() else "No .env file found - copy .env.example to .env first. "
            raise ConfigurationError(f"{prefix}Missing required setting(s): {names}.", hint=hints)

    def register_secrets_for_redaction(self) -> None:
        for secret in (self.supabase_db_url, self.ollama_api_key, self.app_api_key, self.supabase_key):
            if secret is not None:
                register_secret(secret.get_secret_value())
        if self.supabase_db_url is not None:
            # also mask just the password portion of the connection string
            try:
                from sqlalchemy.engine import make_url

                password = make_url(self.supabase_db_url.get_secret_value()).password
                register_secret(password)
            except Exception:  # noqa: BLE001 - malformed URL is reported elsewhere
                pass

    # ------------------------------------------------------------------ off-peak
    def off_peak_window(self) -> tuple[time, time]:
        def parse(value: str) -> time:
            try:
                hour, minute = value.strip().split(":")
                return time(int(hour), int(minute))
            except Exception as exc:  # noqa: BLE001
                raise ConfigurationError(
                    f"Invalid off-peak time '{value}'.", hint="Use 24h HH:MM, e.g. OFFPEAK_START=22:00."
                ) from exc

        return parse(self.offpeak_start), parse(self.offpeak_end)

    def is_off_peak(self, now: datetime | None = None) -> bool:
        """True when inside the configured quiet window (always True if the feature is off)."""
        if not self.offpeak_enabled:
            return True
        start, end = self.off_peak_window()
        try:
            zone = ZoneInfo(self.offpeak_tz)
        except Exception as exc:  # noqa: BLE001
            raise ConfigurationError(f"Unknown OFFPEAK_TZ '{self.offpeak_tz}'.", hint="Use an IANA name.") from exc
        current = (now or datetime.now(zone)).astimezone(zone).time()
        if start <= end:
            return start <= current < end
        return current >= start or current < end  # window wraps past midnight


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.register_secrets_for_redaction()
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()
