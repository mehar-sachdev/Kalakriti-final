"""Feature 2 (database-backed conversation memory) and Feature 4 (competitor-price routing)
end to end through RAGEngine.query(), using FakeConversationStore so no real Postgres is
needed, plus FakeIndex/FakeLLM exactly as the rest of tests/test_engine.py does.
"""
import pytest

from backend.models.schemas import QueryRequest
from backend.rag import products as product_catalog
from backend.rag.engine import RAGEngine
from tests.fakes import FakeConversationStore, FakeIndex, FakeLLM, FakeRegistry, node


def make(settings, nodes=(), answer="Here you go [1].", store=None):
    llm = FakeLLM(answer)
    conversations = store if store is not None else FakeConversationStore()
    engine = RAGEngine(
        settings, embed_model=object(), vector_store=object(), registry=FakeRegistry(),
        llm_gateway=llm, conversations=conversations,
    )
    engine._index = FakeIndex(list(nodes))
    return engine, llm, conversations


DUPATTA_NODE = node(
    "Banarasi Silk Dupatta is a pure silk handloom textile from Varanasi.", 0.9,
    dept="product", dept_name="Product", doc="01_banarasi_silk_dupatta.docx", code=None,
)


# ---------------------------------------------------------------------------- Feature 2: conversation memory
def test_session_id_is_generated_when_absent_and_echoed_back(make_settings):
    engine, _, _ = make(make_settings(similarity_cutoff=0.0), [DUPATTA_NODE])
    result = engine.query(QueryRequest(question="Tell me about the Banarasi Silk Dupatta."))
    assert result.session_id


def test_explicit_session_id_is_echoed_back_unchanged(make_settings):
    engine, _, _ = make(make_settings(similarity_cutoff=0.0), [DUPATTA_NODE])
    result = engine.query(QueryRequest(question="Tell me about the Banarasi Silk Dupatta.", session_id="abc123"))
    assert result.session_id == "abc123"


def test_messages_are_stored_with_product_ids(make_settings):
    engine, _, store = make(make_settings(similarity_cutoff=0.0), [DUPATTA_NODE])
    engine.query(QueryRequest(question="Tell me about the Banarasi Silk Dupatta.", session_id="sess1"))
    stored = store.recent_messages("sess1")
    roles = [m["role"] for m in stored]
    assert roles == ["user", "assistant"]
    assert stored[0]["content"] == "Tell me about the Banarasi Silk Dupatta."
    assert 1 in stored[1]["product_ids"]


def test_followup_pronoun_is_resolved_end_to_end_through_the_engine(make_settings):
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [DUPATTA_NODE])
    engine.query(QueryRequest(question="Tell me about the Banarasi Silk Dupatta.", session_id="sess2"))

    engine.query(QueryRequest(question="What is its price?", session_id="sess2"))
    second_call_user_text = llm.calls[-1][1]
    assert "Banarasi Silk Dupatta" in second_call_user_text
    assert "What is its price?" not in second_call_user_text  # the pronoun was replaced before the LLM ever saw it


def test_no_history_leaves_a_pronoun_question_unresolved(make_settings):
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [DUPATTA_NODE])
    engine.query(QueryRequest(question="What is its price?", session_id="fresh-session"))
    assert "What is its price?" in llm.calls[-1][1]


def test_conversation_storage_failure_never_breaks_the_chat(make_settings):
    broken_store = FakeConversationStore(fail=True)
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [DUPATTA_NODE], store=broken_store)
    result = engine.query(QueryRequest(question="Tell me about the Banarasi Silk Dupatta.", session_id="sess3"))
    assert result.answer and llm.calls  # the chat still worked despite the storage layer being broken


def test_typo_corrected_query_reaches_the_llm(make_settings):
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [DUPATTA_NODE])
    engine.query(QueryRequest(question="Tell me about the Banarasi silk dupata."))
    assert "Dupatta" in llm.calls[-1][1]


def test_scenario_c_three_turn_chain_ending_in_competitor_comparison(make_settings, monkeypatch):
    import backend.rag.engine as engine_module

    monkeypatch.setattr(
        engine_module, "retrieve_live_competitor_price",
        lambda *args: (None, "Live competitor research is not configured; the Kalakriti answer is still available."),
    )
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [DUPATTA_NODE])
    sid = "sess-c"
    engine.query(QueryRequest(question="Tell me about the Banarasi Silk Dupatta.", session_id=sid))
    engine.query(QueryRequest(question="What is its price?", session_id=sid))
    result = engine.query(QueryRequest(question="Is it cheaper than the competitor?", session_id=sid))

    assert result.products and result.products[0].product_id == 1
    assert "Illustrative" in result.answer or "competitor" in result.answer.lower()


# ---------------------------------------------------------------------------- Feature 4: competitor pricing
def test_largest_difference_question_returns_structured_multi_product_answer(make_settings):
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [])
    result = engine.query(QueryRequest(question="Which product has the largest competitor price difference?"))
    assert "name one Kalakriti catalogue product" not in result.answer
    assert result.products
    expected = product_catalog.largest_price_difference(limit=5)[0]
    assert result.products[0].product_id == expected["product_id"]


def test_cheaper_than_competitor_list_question_returns_multiple_products(make_settings):
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [])
    result = engine.query(QueryRequest(question="Which products are cheaper than the competitor reference price?"))
    assert "name one Kalakriti catalogue product" not in result.answer
    assert len(result.products) > 1


def test_unnamed_singular_live_price_question_still_asks_for_clarification(make_settings):
    """Regression guard: the multi-product routing fix must not swallow the genuinely
    unnamed single-product live-price case."""
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [])
    result = engine.query(QueryRequest(question="What is the current competitor price?"))
    assert "name one Kalakriti catalogue product" in result.answer
    assert not result.products and not llm.calls


def test_illustrative_fallback_shown_when_live_lookup_is_unavailable(make_settings, monkeypatch):
    import backend.rag.engine as engine_module

    monkeypatch.setattr(
        engine_module, "retrieve_live_competitor_price",
        lambda *args: (None, "Live competitor research is not configured; the Kalakriti answer is still available."),
    )
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [DUPATTA_NODE])
    result = engine.query(QueryRequest(question="Is the Banarasi Silk Dupatta cheaper than the competitor?"))
    assert "Illustrative / Academic Demonstration Data" in result.answer
    assert result.products[0].competitor_price_inr == 5380
    assert result.products[0].competitor_price_is_illustrative is True


def test_no_competitor_information_message_for_a_product_with_none(make_settings, monkeypatch):
    import backend.rag.engine as engine_module

    monkeypatch.setattr(
        engine_module, "retrieve_live_competitor_price",
        lambda *args: (None, "Live competitor research is not configured; the Kalakriti answer is still available."),
    )
    demo_product = next(p for p in product_catalog.load_catalog() if p.get("competitor_price_inr") is None)
    demo_node = node(f"{demo_product['name']} catalogue listing.", 0.9, dept="product", dept_name="Product",
                      doc=f"{demo_product['product_id']:02d}_x.docx", code=None)
    engine, llm, _ = make(make_settings(similarity_cutoff=0.0), [demo_node])
    result = engine.query(QueryRequest(question=f"Is the {demo_product['name']} cheaper than the competitor?"))
    assert "No competitor" in result.answer
    assert result.products[0].competitor_price_inr is None
