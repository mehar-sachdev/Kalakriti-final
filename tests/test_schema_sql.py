from pathlib import Path

import pytest

from backend.config import PROJECT_ROOT, Settings
from backend.database.connection import safe_identifier, to_async_url, to_sync_url, explain_db_error
from backend.database.schema import MIGRATION_NAMES, chunk_table_name, render_migrations
from backend.exceptions import ConfigurationError


def defaults():
    return Settings(_env_file=None)


def test_checked_in_migrations_match_the_generator():
    """If this fails run: python scripts/setup_database.py --write-migrations"""
    rendered = render_migrations(defaults())
    for name in MIGRATION_NAMES:
        on_disk = (PROJECT_ROOT / "supabase" / "migrations" / name).read_text(encoding="utf-8")
        assert on_disk == rendered[name], name


def test_sql_creates_hnsw_index_rls_and_private_schema():
    sql = "\n".join(render_migrations(defaults()).values())
    assert "using hnsw (embedding vector_cosine_ops)" in sql and "vector(384)" in sql
    assert "create schema if not exists rag" in sql
    # 2 original tables (chunks, documents) + 2 conversation-memory tables (conversations,
    # messages) added for database-backed chat context.
    assert sql.count("enable row level security") == 4 and "revoke all on schema rag" in sql
    assert "'anon'" in sql and "'authenticated'" in sql
    assert "create table if not exists rag.conversations" in sql
    assert "create table if not exists rag.messages" in sql
    for key in ("department_slug", "document_id", "document_type", "source_filename", "doc_code"):
        assert f"metadata_ ->> '{key}'" in sql


def test_dimension_follows_the_configured_model():
    s = Settings(_env_file=None, embedding_model="BAAI/bge-base-en-v1.5")
    assert "vector(768)" in render_migrations(s)["20260920000002_create_rag_tables.sql"]


def test_chunk_table_matches_pgvectorstore_prefix():
    assert chunk_table_name(defaults()) == "data_kalakriti_chunks"


@pytest.mark.parametrize("bad", ["rag; drop table x", "Rag", "a-b", "1abc", "x y", ""])
def test_sql_identifiers_are_validated(bad):
    with pytest.raises(ConfigurationError):
        safe_identifier(bad)
    with pytest.raises(ConfigurationError):
        render_migrations(Settings(_env_file=None, db_schema=bad))


def test_url_conversion_keeps_credentials_and_handles_ssl():
    url = "postgresql://postgres.abc:p%40ss@aws-0-x.pooler.supabase.com:5432/postgres?sslmode=require"
    assert to_sync_url(url).startswith("postgresql+psycopg2://postgres.abc:p%40ss@")
    asyncpg = to_async_url(url)
    assert asyncpg.startswith("postgresql+asyncpg://") and "ssl=require" in asyncpg and "sslmode" not in asyncpg
    assert to_sync_url("postgres://u:p@h/db").startswith("postgresql+psycopg2://")


def test_malformed_url_gives_actionable_error():
    with pytest.raises(ConfigurationError) as exc:
        to_sync_url("not a url")
    assert "URL-encode" in exc.value.hint


@pytest.mark.parametrize("raw,needle", [
    ("FATAL: password authentication failed for user postgres", "password"),
    ("FATAL: Tenant or user not found", "postgres.<project-ref>"),
    ("could not translate host name db.x.supabase.co", "Host name"),
    ("connection to server failed: Network is unreachable", "IPv4"),
    ('extension "vector" is not available', "pgvector"),
])
def test_database_errors_are_translated(raw, needle):
    err = explain_db_error(Exception(raw))
    assert needle in err.hint


def test_database_error_messages_never_contain_the_password():
    from backend.logging_config import register_secret

    register_secret("hunter2hunter2")
    err = explain_db_error(Exception("connection to postgresql://u:hunter2hunter2@host failed"))
    assert "hunter2hunter2" not in err.message
