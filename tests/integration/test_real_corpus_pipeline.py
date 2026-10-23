"""End to end against the REAL 78-document corpus (documents/) and a real Postgres + pgvector.

Uses the deterministic hash embedding (lexical) - this proves the plumbing (parsing, indexing,
metadata filters, the structured product layer) against real data, not semantic retrieval
quality, which needs the real bge-small model and is exercised separately.
"""
import pytest
from sqlalchemy import text

pytest.importorskip("docling")
from backend.database.connection import check_database, get_engine
from backend.database.schema import render_migrations
from backend.ingestion.manifest import Manifest
from backend.ingestion.pipeline import parse_documents
from backend.models.schemas import QueryRequest
from backend.rag.engine import RAGEngine
from backend.rag.indexer import Indexer
from tests.fakes import FakeLLM


@pytest.fixture(scope="module")
def indexed_db(real_env, tmp_path_factory):
    url = real_env.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    from backend.config import PROJECT_ROOT, Settings

    processed = tmp_path_factory.mktemp("processed_it")
    s = Settings(
        _env_file=None, supabase_db_url=url, db_schema="rag_it_kalakriti", embedding_provider="hash",
        similarity_cutoff=0.0, ollama_api_key="k" * 12, raw_dir=PROJECT_ROOT / "documents",
        processed_dir=processed, reports_dir=processed / "reports", log_dir=processed / "logs",
        frontend_dir=PROJECT_ROOT / "frontend", enable_parser_fallback=True,
    )
    engine = get_engine(s)
    with engine.begin() as conn:
        conn.execute(text("drop schema if exists rag_it_kalakriti cascade"))
    for sql in render_migrations(s).values():
        with engine.begin() as conn:
            conn.exec_driver_sql(sql.replace("%", "%%"))
    summary = parse_documents(s, s.raw_dir, s.processed_dir)
    assert summary.count("failed") == 0, [r.reason for r in summary.results if r.status == "failed"]
    manifest = Manifest.load(s.processed_dir / "manifest.json")
    result = Indexer(s).index_documents(manifest, s.processed_dir)
    assert not result.failed, result.failed
    yield s
    with engine.begin() as conn:
        conn.execute(text("drop schema if exists rag_it_kalakriti cascade"))


def test_all_78_real_documents_parse_and_index(indexed_db):
    manifest = Manifest.load(indexed_db.processed_dir / "manifest.json")
    assert len(manifest.successful()) == 165


def test_database_health(indexed_db):
    assert check_database(indexed_db) == ("ok", None)


def test_product_lookup_retrieves_its_own_document(indexed_db):
    engine = RAGEngine(indexed_db, llm_gateway=FakeLLM("answer [1]."))
    nodes = engine.retrieve("Chikankari Embroidered Kurta", top_k=3)
    assert nodes and nodes[0].node.metadata["source_path"] == "product/02_chikankari_embroidered_kurta.docx"
    assert nodes[0].node.metadata.get("product_id") == "2"


def test_structured_facets_are_correct_regardless_of_embedding_quality(indexed_db):
    """The region/city/price/competitor questions must be answered from exact structured data
    (backend/rag/products.py), not from vector search - checked here against the real index."""
    engine = RAGEngine(indexed_db, llm_gateway=FakeLLM("answer [1]."))
    r = engine.query(QueryRequest(question="Show me products from Jaipur"))
    # The catalogue has grown since this assertion was first written (60 -> 146 products,
    # including later "academic demo" items also set in Jaipur) - check containment and the
    # facet layer's own limit rather than a frozen exact id set that will drift again.
    assert {31, 33, 36, 37}.issubset({p.product_id for p in r.products})
    assert all(p.city == "Jaipur" for p in r.products)
    assert len(r.products) <= 8
    r = engine.query(QueryRequest(question="Which crafts come from Rajasthan?"))
    assert len(r.products) == 8 and all(p.region == "Rajasthan" for p in r.products)
    r = engine.query(QueryRequest(question="Show me handmade products under ₹3000"))
    assert r.products and all(p.price_inr <= 3000 for p in r.products)
    r = engine.query(QueryRequest(question="Compare the Banarasi Silk Dupatta with the competitor reference price."))
    assert len(r.products) == 1 and r.products[0].product_id == 1 and r.products[0].competitor_price_is_illustrative


def test_competitor_pricing_document_is_retrievable(indexed_db):
    engine = RAGEngine(indexed_db, llm_gateway=FakeLLM("answer [1]."))
    nodes = engine.retrieve("illustrative academic competitor reference pricing methodology", top_k=5)
    assert any("competitor" in n.node.metadata.get("source_path", "") for n in nodes)


def test_artisan_and_craft_documents_are_indexed(indexed_db):
    engine = RAGEngine(indexed_db, llm_gateway=FakeLLM("answer [1]."))
    nodes = engine.retrieve("Lucknow Chikankari Collective artisan", top_k=5)
    assert any(n.node.metadata.get("source_path", "").startswith("artisan/") for n in nodes)


# ---------------------------------------------------------------------------- professor's scenarios A-G, against the
# real indexed 146-product corpus + real Postgres conversation tables. Text generation itself needs a real Ollama
# Cloud key (FakeLLM stands in for it here, same as the rest of this file) - everything else (retrieval, the
# structured product/competitor layer, typo correction, conversation memory and follow-up resolution) runs for real.
@pytest.fixture
def conv_store(indexed_db):
    from backend.database.conversations import ConversationStore

    return ConversationStore(get_engine(indexed_db), indexed_db)


def test_scenario_a_normal_question_about_the_dupatta(indexed_db):
    engine = RAGEngine(indexed_db, llm_gateway=FakeLLM("The Banarasi Silk Dupatta is a silk handloom piece [1]."))
    r = engine.query(QueryRequest(question="Tell me about the Banarasi Silk Dupatta."))
    assert r.grounded and r.products and r.products[0].product_id == 1


def test_scenario_b_same_question_with_a_typo(indexed_db):
    engine = RAGEngine(indexed_db, llm_gateway=FakeLLM("The Banarasi Silk Dupatta is a silk handloom piece [1]."))
    r = engine.query(QueryRequest(question="Tell me about the Banarasi silk dupata."))
    assert r.grounded and r.products and r.products[0].product_id == 1


def test_scenario_c_followup_chain_ending_in_competitor_comparison(indexed_db, conv_store, monkeypatch):
    import backend.rag.engine as engine_module

    monkeypatch.setattr(
        engine_module, "retrieve_live_competitor_price",
        lambda *args: (None, "Live competitor research is not configured; the Kalakriti answer is still available."),
    )
    engine = RAGEngine(indexed_db, llm_gateway=FakeLLM("Here is what I found [1]."), conversations=conv_store)
    sid = "it-scenario-c"
    engine.query(QueryRequest(question="Tell me about the Banarasi Silk Dupatta.", session_id=sid))
    engine.query(QueryRequest(question="What is its price?", session_id=sid))
    r = engine.query(QueryRequest(question="Is it cheaper than the competitor?", session_id=sid))
    assert r.products and r.products[0].product_id == 1
    assert "Illustrative" in r.answer


def test_scenario_d_region_then_cheaper_then_tell_me_more(indexed_db, conv_store):
    engine = RAGEngine(indexed_db, llm_gateway=FakeLLM("Here is what I found [1]."), conversations=conv_store)
    sid = "it-scenario-d"
    first = engine.query(QueryRequest(question="Show me products from Rajasthan.", session_id=sid))
    assert first.products
    second = engine.query(QueryRequest(question="Which one is cheaper?", session_id=sid))
    assert second.products
    cheapest_id = min(first.products, key=lambda p: p.price_inr).product_id
    assert second.products[0].product_id == cheapest_id
    third = engine.query(QueryRequest(question="Tell me more about it.", session_id=sid))
    assert third.products and third.products[0].product_id == cheapest_id


def test_scenario_e_direct_competitor_comparison(indexed_db, monkeypatch):
    import backend.rag.engine as engine_module

    monkeypatch.setattr(
        engine_module, "retrieve_live_competitor_price",
        lambda *args: (None, "Live competitor research is not configured; the Kalakriti answer is still available."),
    )
    engine = RAGEngine(indexed_db, llm_gateway=FakeLLM("Here is the comparison [1]."))
    r = engine.query(QueryRequest(question="Compare Banarasi Silk Dupatta with competitor pricing."))
    assert r.products and r.products[0].product_id == 1
    assert "Illustrative" in r.answer


# Scenario G (refusing an out-of-knowledge-base question) is NOT meaningfully testable against
# this fixture: it deliberately uses the deterministic hash embedding with similarity_cutoff=0.0
# so every other test here can check retrieval plumbing against real data, but that also means
# nothing is ever filtered out as "irrelevant" - every query gets some chunk back. The real
# refusal behaviour (nothing retrieved -> fixed INSUFFICIENT_INFO_ANSWER, LLM never called) is
# covered precisely at the unit level instead: see
# tests/test_engine.py::test_no_relevant_chunks_skips_the_llm_entirely, which uses an empty
# FakeIndex to simulate genuinely no matching documents.

