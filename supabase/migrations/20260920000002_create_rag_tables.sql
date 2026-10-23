-- Private schema for the RAG store.  It is deliberately NOT one of the schemas
-- Supabase exposes through its REST API, so the anon/authenticated keys cannot reach it.
create schema if not exists rag;

-- Chunk store.  Column layout = LlamaIndex PGVectorStore(use_jsonb=True).
-- vector(384) must equal the embedding model's dimensionality (BAAI/bge-small-en-v1.5).
create table if not exists rag.data_kalakriti_chunks (
    id          bigserial primary key,
    text        varchar not null,
    metadata_   jsonb,
    node_id     varchar,
    embedding   vector(384)
);

-- Approximate nearest-neighbour search (cosine distance).
create index if not exists data_kalakriti_chunks_embedding_idx
    on rag.data_kalakriti_chunks using hnsw (embedding vector_cosine_ops)
    with (m = 16, ef_construction = 64);

-- Metadata filters (department, document, type, file, code) run against JSONB keys.
create index if not exists kalakriti_chunks_idx_department_slug_text on rag.data_kalakriti_chunks ((((metadata_ ->> 'department_slug')::varchar)));
create index if not exists kalakriti_chunks_idx_document_id_text on rag.data_kalakriti_chunks ((((metadata_ ->> 'document_id')::varchar)));
create index if not exists kalakriti_chunks_idx_document_type_text on rag.data_kalakriti_chunks ((((metadata_ ->> 'document_type')::varchar)));
create index if not exists kalakriti_chunks_idx_source_filename_text on rag.data_kalakriti_chunks ((((metadata_ ->> 'source_filename')::varchar)));
create index if not exists kalakriti_chunks_idx_doc_code_text on rag.data_kalakriti_chunks ((((metadata_ ->> 'doc_code')::varchar)));
create index if not exists kalakriti_chunks_idx_product_id_text on rag.data_kalakriti_chunks ((((metadata_ ->> 'product_id')::varchar)));
create index if not exists kalakriti_chunks_idx_city_text on rag.data_kalakriti_chunks ((((metadata_ ->> 'city')::varchar)));
create index if not exists kalakriti_chunks_idx_1 on rag.data_kalakriti_chunks ((metadata_ ->> 'ref_doc_id'));

-- Document registry: one row per indexed source document.
create table if not exists rag.documents (
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
    metadata            jsonb not null default '{}'::jsonb
);
create index if not exists documents_department_idx on rag.documents (department_slug);
