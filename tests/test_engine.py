import pytest

from backend.exceptions import OffPeakRestricted
from backend.models.schemas import QueryRequest
from backend.rag.engine import RAGEngine
from backend.rag.prompts import INSUFFICIENT_INFO_ANSWER
from backend.rag.retrieval import UnknownDepartment
from tests.fakes import FakeIndex, FakeLLM, FakeRegistry, node

FIN = node("Expense claims above ₹5,000 need manager approval and above ₹25,000 need director approval.", 0.82)
FIN2 = node("Financial controls: payments above ₹1,00,000 need CFO approval; above ₹10,000 need finance head.", 0.74, code="KAL-FIN-POL-010", doc="10_Controls.docx", page=1, section="4. Approval matrix")
HR = node("Employees get 12 days of casual leave per year.", 0.66, dept="hr", dept_name="HR", code="KAL-HR-POL-002", doc="02_Leave.docx", page=1)
LOW = node("Barely related vendor text.", 0.10, dept="legal-and-compliance", dept_name="Legal & Compliance", code="KAL-LEG-POL-001", doc="01_Vendor.docx", page=1)


def make(settings, nodes, answer="Claims above ₹5,000 need manager approval [1]."):
    llm = FakeLLM(answer)
    engine = RAGEngine(settings, embed_model=object(), vector_store=object(), registry=FakeRegistry(), llm_gateway=llm)
    engine._index = FakeIndex(nodes)
    return engine, llm


def ask(engine, question="What are the approval limits?", **kw):
    return engine.query(QueryRequest(question=question, **kw))


def test_answer_has_grounded_sources_and_timings(make_settings):
    engine, llm = make(make_settings(similarity_cutoff=0.25), [FIN, FIN2, HR, LOW])
    r = ask(engine)
    assert r.grounded and r.retrieved_count == 3          # LOW is below the 0.25 cut-off
    assert [s.citation_id for s in r.sources] == [1, 2, 3] and r.sources[0].doc_code == "KAL-FIN-POL-009"
    assert [s.used_in_answer for s in r.sources] == [True, False, False]   # only [1] was cited
    assert r.model == "gpt-oss:20b" and r.timings.total_ms >= r.timings.retrieval_ms
    system, user = llm.calls[0]
    assert "[1] Finance" in user and "Question: What are the approval limits?" in user and "₹5,000" in user


def test_department_filter_isolates_sources(make_settings):
    engine, _ = make(make_settings(), [FIN, FIN2, HR])
    r = ask(engine, department="Finance")
    assert {s.department_slug for s in r.sources} == {"finance"} and r.applied_filters == {"department": "finance"}
    r = ask(engine, department="hr")
    assert {s.department_slug for s in r.sources} == {"hr"}


def test_partial_department_name_and_unknown_department(make_settings):
    engine, _ = make(make_settings(), [FIN, HR])
    assert ask(engine, department="Sales").applied_filters == {"department": "sales-and-customer"}
    with pytest.raises(UnknownDepartment):
        ask(engine, department="Astrology")


def test_department_detected_from_question_when_none_selected(make_settings):
    engine, _ = make(make_settings(), [FIN, HR])
    r = ask(engine, "Show me the Finance department's reimbursement policy.")
    assert r.applied_filters == {"department": "finance", "department_inferred": True}
    assert {s.department_slug for s in r.sources} == {"finance"}


def test_detection_can_be_switched_off_and_explicit_all_wins(make_settings):
    engine, _ = make(make_settings(auto_department_detection=False), [FIN, HR])
    assert ask(engine, "Show me the Finance department's policy").applied_filters == {}
    engine, _ = make(make_settings(), [FIN, HR])
    assert ask(engine, "Show me the Finance department's policy", department="all").applied_filters == {}


def test_no_relevant_chunks_skips_the_llm_entirely(make_settings):
    engine, llm = make(make_settings(similarity_cutoff=0.9), [FIN, HR])
    r = ask(engine, "What is the capital of France?")
    assert r.answer == INSUFFICIENT_INFO_ANSWER and not r.grounded and r.sources == [] and r.model is None
    assert llm.calls == []  # no quota spent, nothing to hallucinate from


def test_model_saying_insufficient_marks_answer_ungrounded(make_settings):
    engine, _ = make(make_settings(), [FIN], answer="The available documents do not provide sufficient information to answer this.")
    r = ask(engine)
    assert r.grounded is False and all(not s.used_in_answer for s in r.sources)


def test_uncited_answer_marks_all_sources_consulted(make_settings):
    engine, _ = make(make_settings(), [FIN, FIN2], answer="Limits are described in the policy.")
    assert all(s.used_in_answer for s in ask(engine).sources)


def test_duplicate_chunks_are_removed(make_settings):
    dup = node(FIN.node.get_content(), 0.80, dept="finance", doc="XLSX-copy.xlsx", code="KAL-FIN-XLSX-009A", page=None)
    engine, _ = make(make_settings(), [FIN, dup, FIN2])
    assert [s.doc_code for s in ask(engine).sources] == ["KAL-FIN-POL-009", "KAL-FIN-POL-010"]


def test_top_k_override_and_document_type_canonicalisation(make_settings):
    engine, _ = make(make_settings(top_k=6), [FIN, FIN2, HR])
    assert len(ask(engine, top_k=1).sources) == 1
    r = ask(engine, document_type="policy")
    assert r.applied_filters["document_type"] == "Policy"
    assert engine._index.log[-1]["filters"].filters[0].value == "Policy"


def test_off_peak_enforced_and_advisory(make_settings, monkeypatch):
    engine, llm = make(make_settings(offpeak_enabled=True, offpeak_enforce=True), [FIN])
    monkeypatch.setattr(type(engine.settings), "is_off_peak", lambda self, now=None: False)
    with pytest.raises(OffPeakRestricted) as exc:
        ask(engine)
    assert exc.value.http_status == 429 and "22:00" in exc.value.hint and llm.calls == []
    engine.settings.__dict__["offpeak_enforce"] = False
    r = ask(engine)
    assert r.off_peak is False and "off-peak" in r.notice.lower()


def test_context_is_capped(make_settings):
    big = [node("filler sentence. " * 100, 0.9 - i / 100, doc=f"d{i}.docx", code=f"K-{i:03d}-AAA-001") for i in range(6)]
    engine, llm = make(make_settings(max_context_chars=3000), big)
    r = ask(engine)
    assert len(llm.calls[0][1]) < 3600 and len(r.sources) < 6


def test_web_research_only_runs_for_named_live_price_question(make_settings, monkeypatch):
    import backend.rag.engine as engine_module

    answer = "The Banarasi Silk Dupatta is listed in the catalogue."
    engine, llm = make(make_settings(similarity_cutoff=0.0), [
        node("Banarasi Silk Dupatta is a pure silk handloom textile.", 0.8, dept="product", dept_name="Product",
             doc="01_banarasi_silk_dupatta.docx", code=None)
    ], answer=answer)
    calls = []
    monkeypatch.setattr(engine_module, "retrieve_live_competitor_price", lambda *args: (
        calls.append(args) or ({
            "competitor_name": "Khadi India", "competitor_product_name": "Banarasi Silk Dupatta",
            "competitor_price_inr": 871, "source_url": "https://shop.example/item", "price_checked_at": "2026-09-28T00:00:00+00:00",
            "comparison_type": "same_product", "price_verified": True,
            "verification_status": "verified_from_fetched_page",
        }, None)
    ))

    normal = ask(engine, "Tell me about the Banarasi Silk Dupatta")
    assert calls == [] and normal.answer == answer and not normal.live_competitor_prices

    live = ask(engine, "Compare the Banarasi Silk Dupatta with competitors")
    assert len(calls) == 1 and live.products[0].competitor_price_inr is None
    assert live.live_competitor_prices[0].competitor_price_inr == 871
    assert "KALAKRITI PRICE" in live.answer and "LIVE COMPETITOR PRICE" in live.answer


def test_unnamed_live_price_request_does_not_fall_back_to_illustrative_data(make_settings):
    engine, llm = make(make_settings(), [FIN])
    result = ask(engine, "What is the current competitor price?")
    assert "name one Kalakriti catalogue product" in result.answer
    assert not result.products and not result.live_competitor_prices and not llm.calls


def test_partial_product_phrase_triggers_live_price_path(make_settings, monkeypatch):
    import backend.rag.engine as engine_module

    engine, llm = make(make_settings(similarity_cutoff=0.0), [
        node("Jaipur Blue Pottery Bowl: quartz-based body, hand glazed and painted.", 0.9,
             dept="product", dept_name="Product", doc="31_jaipur_blue_pottery_bowl.docx", code=None)
    ])
    calls = []
    monkeypatch.setattr(engine_module, "retrieve_live_competitor_price", lambda settings, product, question: (
        calls.append((product, question)) or ({
            "competitor_name": "Example Retailer", "competitor_product_name": "Blue pottery bowl",
            "competitor_price_inr": 899, "source_url": "https://shop.example/bowl",
            "price_checked_at": "2026-09-28T00:00:00+00:00", "comparison_type": "comparable_category",
            "price_verified": True, "verification_status": "verified_from_fetched_page",
        }, None)
    ))

    result = ask(engine, "What is the current competitor price for Jaipur Blue Pottery?")

    assert len(calls) == 1 and calls[0][0]["product_id"] == 31
    assert result.products[0].product_id == 31
    assert result.live_competitor_prices[0].competitor_price_inr == 899
    assert "LIVE COMPETITOR PRICE" in result.answer and "Source: https://shop.example/bowl" in result.answer
    assert "never call that verified live price illustrative" in llm.calls[0][0]


def test_verified_live_price_is_returned_even_if_rag_text_is_insufficient(make_settings, monkeypatch):
    import backend.rag.engine as engine_module

    engine, _ = make(make_settings(similarity_cutoff=0.0), [
        node("Jaipur Blue Pottery Bowl", 0.9, dept="product", dept_name="Product",
             doc="31_jaipur_blue_pottery_bowl.docx", code=None)
    ], answer="I could not find this information in the current Kalakriti knowledge base.")
    monkeypatch.setattr(engine_module, "retrieve_live_competitor_price", lambda *args: ({
        "competitor_name": "Verified Shop", "competitor_product_name": "Jaipur blue pottery bowl",
        "competitor_price_inr": 899, "source_url": "https://shop.example/bowl",
        "price_checked_at": "2026-09-28T00:00:00+00:00", "comparison_type": "comparable_category",
        "price_verified": True, "verification_status": "verified_from_fetched_page",
    }, None))

    result = ask(engine, "What is the current competitor price for Jaipur Blue Pottery?")

    assert result.grounded is True
    assert result.products[0].product_id == 31
    assert result.live_competitor_prices[0].price_verified is True
    assert "LIVE COMPETITOR PRICE" in result.answer and "Source: https://shop.example/bowl" in result.answer


def test_live_price_status_reports_verified_and_not_verified(make_settings, monkeypatch):
    import backend.rag.engine as engine_module

    docs = [node("Jaipur Blue Pottery Bowl", 0.9, dept="product", dept_name="Product",
                 doc="31_jaipur_blue_pottery_bowl.docx", code=None)]
    engine, _ = make(make_settings(similarity_cutoff=0.0), docs)
    monkeypatch.setattr(engine_module, "retrieve_live_competitor_price", lambda *args: (
        None, "A current comparable competitor price could not be verified from the available pages."))
    result = ask(engine, "What is the current competitor price for Jaipur Blue Pottery?")
    assert not result.live_competitor_prices
    assert result.live_price_status.verified is False and result.live_price_status.product_id == 31
    assert "could not be verified" in result.live_price_status.message
    normal = ask(engine, "Tell me about the Jaipur Blue Pottery Bowl")
    assert normal.live_price_status is None


def test_web_lookup_crash_or_llm_outage_does_not_break_live_price_answer(make_settings, monkeypatch):
    import backend.rag.engine as engine_module
    from backend.exceptions import RAGError

    docs = [node("Jaipur Blue Pottery Bowl", 0.9, dept="product", dept_name="Product",
                 doc="31_jaipur_blue_pottery_bowl.docx", code=None)]
    engine, llm = make(make_settings(similarity_cutoff=0.0), docs)

    def boom(*args):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(engine_module, "retrieve_live_competitor_price", boom)
    result = ask(engine, "What is the current competitor price for Jaipur Blue Pottery?")
    assert result.live_price_status.verified is False and "temporarily unavailable" in result.live_price_status.message

    monkeypatch.setattr(engine_module, "retrieve_live_competitor_price", lambda *args: ({
        "competitor_name": "Verified Shop", "competitor_product_name": "Blue pottery bowl",
        "competitor_price_inr": 899, "source_url": "https://shop.example/bowl",
        "price_checked_at": "2026-09-28T00:00:00+00:00", "comparison_type": "comparable_category",
        "price_verified": True, "verification_status": "verified_from_fetched_page",
    }, None))
    monkeypatch.setattr(engine.llm, "generate", lambda *a, **k: (_ for _ in ()).throw(RAGError("LLM down")))
    result = ask(engine, "What is the current competitor price for Jaipur Blue Pottery?")
    assert result.live_competitor_prices[0].competitor_price_inr == 899 and result.live_price_status.verified
