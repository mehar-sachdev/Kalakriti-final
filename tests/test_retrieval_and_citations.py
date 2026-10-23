import pytest

from backend.models.schemas import SourceRef
from backend.rag.citations import extract_cited_ids, location_label, make_excerpt, node_to_source, render_sources_text
from backend.rag.prompts import SYSTEM_PROMPT, build_context, format_excerpt_header
from backend.rag.retrieval import (DedupPostprocessor, Dept, UnknownDepartment, build_metadata_filters, infer_department,
                                   relevance_filter, resolve_department)
from tests.fakes import node

D = [Dept("finance", "Finance"), Dept("hr", "HR"), Dept("sales-and-customer", "Sales & Customer"),
     Dept("legal-and-compliance", "Legal & Compliance"), Dept("operations-and-logistics", "Operations & Logistics"),
     Dept("product-and-craft", "Product & Craft")]


@pytest.mark.parametrize("value,slug", [
    ("Finance", "finance"), ("finance", "finance"), ("FINANCE", "finance"), ("Sales & Customer", "sales-and-customer"),
    ("sales-and-customer", "sales-and-customer"), ("Sales", "sales-and-customer"), ("legal", "legal-and-compliance"),
    ("hr", "hr"), ("Logistics", "operations-and-logistics"),
])
def test_resolve_department(value, slug):
    assert resolve_department(value, D) == slug


@pytest.mark.parametrize("value", [None, "", "all", "All Departments", "  ALL "])
def test_all_departments_means_no_filter(value):
    assert resolve_department(value, D) is None


def test_unknown_department_lists_valid_ones():
    with pytest.raises(UnknownDepartment) as exc:
        resolve_department("Astrology", D)
    assert "Finance" in exc.value.hint and exc.value.http_status == 422


def test_ambiguous_department_is_rejected():
    with pytest.raises(UnknownDepartment):
        resolve_department("and", [Dept("a-and-b", "A and B"), Dept("c-and-d", "C and D")])


@pytest.mark.parametrize("q,expected", [
    ("Show me the Finance department's reimbursement policy.", "finance"),
    ("What does the HR team say about leave?", "hr"),
    ("department of Finance travel limits", "finance"),
    ("Finance's approval matrix", "finance"),
    ("What is in the Legal & Compliance department documents?", "legal-and-compliance"),
    ("from the sales documents, what is the return window?", "sales-and-customer"),
])
def test_department_inference_positive(q, expected):
    assert infer_department(q, D).slug == expected


@pytest.mark.parametrize("q", [
    "What is the reimbursement policy?",
    "How do finance and HR departments interact?",   # two departments -> ambiguous -> no filter
    "Tell me about legal risks in general",           # bare word, no department phrasing
    "What is the capital of France?",
])
def test_department_inference_is_conservative(q):
    assert infer_department(q, D) is None


def test_metadata_filters():
    f = build_metadata_filters("finance", "Policy", "x.pdf")
    assert [(x.key, x.value) for x in f.filters] == [("department_slug", "finance"), ("document_type", "Policy"), ("source_filename", "x.pdf")]
    assert build_metadata_filters() is None


def test_relevance_cutoff_and_dedup_keep_best_duplicate():
    a, b, c = node("Refund within 7 working days of return.", 0.8), node("Refund within 7 working days of return.", 0.6, doc="other.xlsx"), node("Completely different topic about vendors.", 0.7)
    kept = DedupPostprocessor().postprocess_nodes([b, a, c])
    assert [round(n.score, 1) for n in kept] == [0.8, 0.7]
    assert len(relevance_filter([a, b, c], 0.65)) == 2


def test_dedup_keeps_similar_but_distinct_chunks():
    a, b = node("Approval limit is ₹5,000 for managers.", 0.9), node("Approval limit is ₹25,000 for directors and heads.", 0.8)
    assert len(DedupPostprocessor().postprocess_nodes([a, b])) == 2


# ---- citations --------------------------------------------------------------------------------
def test_extract_cited_ids():
    assert extract_cited_ids("Limit is ₹5,000 [1][3]. Also [2]. Array a[0] not; [123] ignored") == {1, 2, 3, 0}


def test_excerpt_is_trimmed_on_a_word_boundary():
    out = make_excerpt("word " * 200, 50)
    assert out.endswith("…") and len(out) <= 55 and "  " not in out
    assert make_excerpt("a\n\n b   c", None) == "a b c"


def test_node_to_source_carries_page_sheet_and_status():
    s = node_to_source(1, node("text", 0.83456, page=4))
    assert (s.document, s.page, s.department, s.doc_code, s.status, s.score) == ("Finance/09_Expense_Policy.docx", 4, "Finance", "KAL-FIN-POL-009", "Active", 0.8346)
    x = node_to_source(2, node("text", 0.5, page=None, doc="m.xlsx", sheet_name="Approval Rules"))
    assert x.page is None and x.sheet == "Approval Rules" and location_label(x) == "Sheet: Approval Rules"


def test_render_sources_text_format():
    text = render_sources_text([node_to_source(1, node("t", 0.7, page=4)), node_to_source(2, node("t", 0.6), used=False)])
    assert "Source: Finance/09_Expense_Policy.docx" in text and "Page: 4" in text and "retrieved, not cited" in text
    assert "no relevant documents" in render_sources_text([])


# ---- prompts ------------------------------------------------------------------------------------
def test_system_prompt_forbids_invention_and_requires_citations_and_illustrative_labelling():
    low = SYSTEM_PROMPT.lower()
    for phrase in ("only", "never guess", "square brackets", "conflict", "illustrative", "knowledge base"):
        assert phrase in low, phrase


def test_context_is_numbered_labelled_and_truncated():
    ex = [(i, {"department": "Finance", "title": "Policy", "doc_code": "K-1", "version": "1.1", "status": "Active", "page_number": i, "source_path": "Finance/p.pdf"}, "x" * 400) for i in range(1, 6)]
    ctx, used = build_context(ex, max_chars=1000)
    assert used < 5 and ctx.startswith("[1] Finance | Policy | K-1 v1.1 (Active) | Page 1") and "[2]" in ctx
    assert build_context(ex, 100000)[1] == 5
    assert build_context(ex, 10)[1] == 1  # always keeps at least the best excerpt


def test_excerpt_header_omits_missing_fields():
    assert format_excerpt_header(3, {"department": "HR", "source_filename": "a.xlsx"}) == "[3] HR | a.xlsx"
