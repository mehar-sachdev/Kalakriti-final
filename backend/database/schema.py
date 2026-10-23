"""SQL for the Supabase/Postgres schema (single source of truth).

``supabase/migrations/*.sql`` are generated from this module
(``python scripts/setup_database.py --write-migrations``) and a unit test asserts they
have not drifted.  The chunk table mirrors exactly what LlamaIndex's ``PGVectorStore``
creates for ``use_jsonb=True`` so the store and the migration agree.
"""
from __future__ import annotations

from backend.config import Settings
from backend.database.connection import safe_identifier

MIGRATION_NAMES = [
    "20260920000001_enable_pgvector.sql",
    "20260920000002_create_rag_tables.sql",
    "20260920000003_lock_down_access.sql",
    "20261010000001_create_conversation_tables.sql",
]

INDEXED_METADATA_KEYS = ("department_slug", "document_id", "document_type", "source_filename", "doc_code", "product_id", "city")


def chunk_table_name(settings: Settings) -> str:
    """PGVectorStore prefixes table names with ``data_``."""
    return f"data_{safe_identifier(settings.vector_table)}"


def render_migrations(settings: Settings) -> dict[str, str]:
    schema = safe_identifier(settings.db_schema)
    chunks = chunk_table_name(settings)
    docs = safe_identifier(settings.documents_table)
    vt = safe_identifier(settings.vector_table)
    dim = settings.resolved_embedding_dim

    metadata_indexes = "\n".join(
        f"create index if not exists {vt}_idx_{key}_text on {schema}.{chunks} "
        f"((((metadata_ ->> '{key}')::varchar)));"
        for key in INDEXED_METADATA_KEYS
    )

    enable = """\
-- Enables pgvector.  On Supabase you can also toggle it in Database > Extensions.
create extension if not exists vector;
"""

    tables = f"""\
-- Private schema for the RAG store.  It is deliberately NOT one of the schemas
-- Supabase exposes through its REST API, so the anon/authenticated keys cannot reach it.
create schema if not exists {schema};

-- Chunk store.  Column layout = LlamaIndex PGVectorStore(use_jsonb=True).
-- vector({dim}) must equal the embedding model's dimensionality ({settings.embedding_model}).
create table if not exists {schema}.{chunks} (
    id          bigserial primary key,
    text        varchar not null,
    metadata_   jsonb,
    node_id     varchar,
    embedding   vector({dim})
);

-- Approximate nearest-neighbour search (cosine distance).
create index if not exists {chunks}_embedding_idx
    on {schema}.{chunks} using hnsw (embedding vector_cosine_ops)
    with (m = 16, ef_construction = 64);

-- Metadata filters (department, document, type, file, code) run against JSONB keys.
{metadata_indexes}
create index if not exists {vt}_idx_1 on {schema}.{chunks} ((metadata_ ->> 'ref_doc_id'));

-- Document registry: one row per indexed source document.
create table if not exists {schema}.{docs} (
    document_id         text primary key,
    title               text,
    doc_code            text,
    department          text not null,
    department_slug     text not null,
    source_filename     text not null,
    source_path         text not null,
    file_type           text not null,
    document_type       text,
    version             text,
    status              text,
    classification      text,
    page_count          integer,
    chunk_count         integer not null default 0,
    checksum_sha256     text not null,
    parser              text,
    embedding_signature text not null,
    chunk_config        text not null,
    indexed_at          timestamptz not null default now(),
    metadata            jsonb not null default '{{}}'::jsonb
);
create index if not exists {docs}_department_idx on {schema}.{docs} (department_slug);
"""

    security = f"""\
-- Defence in depth.  The backend connects with the database owner role (which bypasses
-- RLS); every other role, including Supabase's anon and authenticated, gets nothing.
alter table {schema}.{chunks} enable row level security;
alter table {schema}.{docs} enable row level security;

do $$
declare r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on schema {schema} from %I', r);
            execute format('revoke all on all tables in schema {schema} from %I', r);
            execute format('revoke all on all sequences in schema {schema} from %I', r);
        end if;
    end loop;
end $$;
"""
    conversations = f"""\
-- Database-backed chat memory (so the chatbot's follow-up/context handling survives page
-- reloads and works the same from any device), added for: database-backed conversation
-- context. Lives in the same private {schema} schema as the chunk/document tables above -
-- no new database, and this migration only ADDs tables, it never touches the existing ones.
create table if not exists {schema}.conversations (
    session_id       text primary key,
    created_at       timestamptz not null default now(),
    last_active_at   timestamptz not null default now(),
    last_product_ids integer[] not null default array[]::integer[]
);

create table if not exists {schema}.messages (
    id          bigserial primary key,
    session_id  text not null references {schema}.conversations(session_id) on delete cascade,
    role        text not null check (role in ('user', 'assistant')),
    content     text not null,
    product_ids integer[] not null default array[]::integer[],
    sources     jsonb,
    created_at  timestamptz not null default now()
);
create index if not exists messages_session_created_idx
    on {schema}.messages (session_id, created_at);

alter table {schema}.conversations enable row level security;
alter table {schema}.messages enable row level security;

do $$
declare r text;
begin
    foreach r in array array['anon', 'authenticated'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on {schema}.conversations from %I', r);
            execute format('revoke all on {schema}.messages from %I', r);
        end if;
    end loop;
end $$;
"""

    return dict(zip(MIGRATION_NAMES, [enable, tables, security, conversations]))
