"""Postgres/Supabase connectivity helpers.

The backend talks to Supabase *only* through a Postgres connection string held in
``SUPABASE_DB_URL`` (server side).  The Supabase REST/anon/service-role keys are
never needed and never leave the server.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError, OperationalError, SQLAlchemyError

from backend.config import Settings
from backend.exceptions import ConfigurationError, DatabaseError
from backend.logging_config import redact

logger = logging.getLogger(__name__)


def _parsed(url: str):
    try:
        return make_url(url.strip())
    except ArgumentError as exc:
        raise ConfigurationError(
            "SUPABASE_DB_URL is not a valid database URL.",
            hint="Expected postgresql://USER:PASSWORD@HOST:5432/postgres . URL-encode special characters in the password (@ -> %40).",
        ) from exc


def to_sync_url(url: str) -> str:
    parsed = _parsed(url)
    return parsed.set(drivername="postgresql+psycopg2").render_as_string(hide_password=False)


def to_async_url(url: str) -> str:
    parsed = _parsed(url).set(drivername="postgresql+asyncpg")
    query = dict(parsed.query)
    sslmode = query.pop("sslmode", None)
    if sslmode:
        query["ssl"] = sslmode
    return parsed.set(query=query).render_as_string(hide_password=False)


@lru_cache(maxsize=4)
def _engine_for(url: str) -> Engine:
    return create_engine(
        to_sync_url(url), pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=1800,
        connect_args={"connect_timeout": 10},
    )


def get_engine(settings: Settings) -> Engine:
    settings.require("index")
    return _engine_for(settings.supabase_db_url.get_secret_value())  # type: ignore[union-attr]


def explain_db_error(exc: Exception) -> DatabaseError:
    """Translate a driver error into a short, secret-free message with a fix."""
    raw = redact(str(exc)).strip().split("\n")[0]
    lowered = raw.lower()
    hint = "Check SUPABASE_DB_URL and that the Supabase project is running (free projects pause after inactivity)."
    if "password authentication failed" in lowered or "authentication failed" in lowered:
        hint = "The database password is wrong. Reset it in Supabase > Project Settings > Database and update .env."
    elif "tenant or user not found" in lowered:
        hint = "With the pooler the user must be 'postgres.<project-ref>', not just 'postgres'."
    elif "could not translate host name" in lowered or "name or service not known" in lowered:
        hint = "Host name not found. Copy the connection string again from Supabase (Session pooler)."
    elif "network is unreachable" in lowered or "cannot assign requested address" in lowered:
        hint = "No IPv6 route (typical in WSL). Use the Session pooler connection string, which works over IPv4."
    elif "timeout" in lowered or "timed out" in lowered:
        hint = "Connection timed out. Check your network/VPN, the port (5432 session pooler) and Supabase project status."
    elif "extension" in lowered and "vector" in lowered:
        hint = "Enable pgvector: run `create extension if not exists vector;` or run scripts/setup_database.py."
    return DatabaseError(f"Database error: {raw[:240]}", hint=hint)


def check_database(settings: Settings) -> tuple[str, str | None]:
    """('ok'|'not_configured'|'error', detail)"""
    if settings.supabase_db_url is None:
        return "not_configured", "SUPABASE_DB_URL is not set."
    try:
        engine = get_engine(settings)
        with engine.connect() as conn:
            conn.execute(text("select 1"))
            has_vector = conn.execute(text("select 1 from pg_extension where extname='vector'")).first()
        if not has_vector:
            return "error", "pgvector extension is not enabled (run scripts/setup_database.py)."
        return "ok", None
    except ConfigurationError as exc:
        return "error", exc.message
    except (OperationalError, SQLAlchemyError) as exc:
        return "error", explain_db_error(exc).message
    except Exception as exc:  # noqa: BLE001
        return "error", explain_db_error(exc).message


_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def safe_identifier(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise ConfigurationError(f"'{name}' is not a valid SQL identifier.", hint="Use lower-case letters, digits and underscores.")
    return name
