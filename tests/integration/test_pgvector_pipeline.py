"""End to end against a real Postgres + pgvector: parse -> migrate -> index -> filtered retrieval.

Uses the deterministic *hash* embedding (lexical), so it verifies plumbing, filters and idempotency,
NOT semantic retrieval quality.  Uses its own schema 'rag_it' and removes it afterwards.
"""
import pytest
from sqlalchemy import text

pytest.importorskip("docling")
from backend.database.connection import check_database, get_engine
from backend.database.registry import DocumentRegistry
from backend.database.schema import render_migrations
from backend.exceptions import IndexingError
from backend.ingestion.manifest import Manifest
from backend.ingestion.pipeline import parse_documents
from backend.rag.engine import RAGEngine
from backend.rag.indexer import Indexer
from backend.models.schemas import QueryRequest
from tests.fakes import FakeLLM


@pytest.fixture
def db(real_env, make_settings, corpus, offline_registry, settings):
    url = real_env.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    s = make_settings(supabase_db_url=url, db_schema="rag_it", similarity_cutoff=0.0, ollama_api_key="k" * 12)
    engine = get_engine(s)
    with engine.begin() as conn:
        conn.execute(text("drop schema if exists rag_it cascade"))
    for sql in render_migrations(s).values():
        with engine.begin() as conn:
            conn.exec_driver_sql(sql.replace("%", "%%"))
    parse_documents(s, corpus, s.processed_dir, registry=offline_registry)
    yield s
    with engine.begin() as conn:
        conn.execute(text("drop schema if exists rag_it cascade"))


def test_database_health(db):
    assert check_database(db) == ("ok", None)


def test_index_is_incremental_and_filters_work(db, corpus):
    indexer = Indexer(db)
    manifest = Manifest.load(db.manifest_path)
    first = indexer.index_documents(manifest, db.processed_dir)
    assert len(first.indexed) == 5 and not first.failed and first.chunks_written >= 5

    again = Indexer(db).index_documents(Manifest.load(db.manifest_path), db.processed_dir)
    assert again.indexed == [] and len(again.skipped) == 5   # idempotent

    engine = RAGEngine(db, llm_gateway=FakeLLM("Answer [1]."))
    everything = engine.retrieve("return policy refund days", top_k=6)
    only_sales = engine.retrieve("return policy refund days", department_slug="sales-and-customer", top_k=6)
    only_fin = engine.retrieve("return policy refund days", department_slug="finance", top_k=6)
    assert {n.node.metadata["department_slug"] for n in everything} >= {"finance", "sales-and-customer"}  # unfiltered search spans departments
    assert only_sales and {n.node.metadata["department_slug"] for n in only_sales} == {"sales-and-customer"}
    assert only_fin and {n.node.metadata["department_slug"] for n in only_fin} == {"finance"}
    vendor = engine.retrieve("vendor paid invoice", department_slug="legal-and-compliance", top_k=3)
    assert vendor and vendor[0].node.metadata["source_filename"] == "vendor_terms.md"

    response = engine.query(QueryRequest(question="How long do refunds take after a return?", department="Sales"))
    assert response.sources and response.sources[0].department_slug == "sales-and-customer"
    assert response.sources[0].page in (1, 2) or response.sources[0].sheet


def test_changed_document_is_reindexed_and_old_chunks_removed(db, corpus, offline_registry):
    Indexer(db).index_documents(Manifest.load(db.manifest_path), db.processed_dir)
    (corpus / "Finance" / "notes.txt").write_text("New rule: claims must be filed within 90 days of purchase.")
    parse_documents(db, corpus, db.processed_dir, registry=offline_registry)
    summary = Indexer(db).index_documents(Manifest.load(db.manifest_path), db.processed_dir)
    assert summary.indexed == ["finance__notes-txt"]
    registry = DocumentRegistry(get_engine(db), db)
    chunks = registry.chunks_for("finance__notes-txt")
    assert len(chunks) == 1 and "90 days" in chunks[0]["text"] and "30 days" not in chunks[0]["text"]


def test_embedding_model_change_is_refused_without_reset(db, make_settings):
    Indexer(db).index_documents(Manifest.load(db.manifest_path), db.processed_dir)
    other = make_settings(supabase_db_url=db.supabase_db_url.get_secret_value(), db_schema="rag_it", embedding_dim=384, embedding_model="different/model", embedding_provider="hash")
    with pytest.raises(IndexingError) as exc:
        Indexer(other).index_documents(Manifest.load(db.manifest_path), db.processed_dir)
    assert "--reset" in exc.value.hint
    reset = Indexer(other).index_documents(Manifest.load(db.manifest_path), db.processed_dir, reset=True)
    assert len(reset.indexed) == 5


def test_prune_removes_vanished_documents(db, corpus, offline_registry):
    Indexer(db).index_documents(Manifest.load(db.manifest_path), db.processed_dir)
    (corpus / "Finance" / "notes.txt").unlink()
    parse_documents(db, corpus, db.processed_dir, registry=offline_registry)
    summary = Indexer(db).index_documents(Manifest.load(db.manifest_path), db.processed_dir, prune=True)
    registry = DocumentRegistry(get_engine(db), db)
    assert summary.pruned == ["finance__notes-txt"] and "finance__notes-txt" not in registry.all_ids()
    assert registry.chunks_for("finance__notes-txt") == []


def test_row_level_security_is_enabled(db):
    Indexer(db)  # creates tables through PGVectorStore if the migration did not
    assert DocumentRegistry(get_engine(db), db).rls_enabled() is True
