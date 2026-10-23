import json
from pathlib import Path

import pytest

from evaluation import metrics as m
from evaluation.evaluate import load_questions, render_markdown

SRC = lambda code, name, dept="finance": {"doc_code": code, "document": f"Finance/{name}", "department_slug": dept}


def test_retrieval_metrics():
    sources = [SRC("KAL-HR-POL-002", "a.docx", "hr"), SRC("KAL-FIN-POL-009", "b.docx"), SRC("KAL-FIN-POL-010", "c.docx")]
    r = m.retrieval_metrics(sources, {"doc_codes": ["KAL-FIN-POL-009", "KAL-FIN-POL-010"]}, k=3)
    assert r == {"hit": 1.0, "rr": 0.5, "precision": pytest.approx(2 / 3), "doc_recall": 1.0}
    assert m.retrieval_metrics(sources[:1], {"doc_codes": ["KAL-FIN-POL-009"]}, k=3)["hit"] == 0.0
    assert m.retrieval_metrics(sources, {}, k=3)["hit"] is None
    assert m.retrieval_metrics(sources, {"filenames": ["B.docx"]}, k=3)["hit"] == 1.0


def test_department_isolation():
    assert m.department_isolation([SRC("a", "a", "hr")], "hr") is True
    assert m.department_isolation([SRC("a", "a", "hr"), SRC("b", "b", "finance")], "hr") is False
    assert m.department_isolation([], None) is None


def test_fact_groups_accept_alternative_spellings():
    score, missing = m.contains_all_groups("Above ₹100,000 and ₹10,000.", [["1,00,000", "100,000"], ["10,000"], ["25,000"]])
    assert score == pytest.approx(2 / 3) and missing == [["25,000"]]
    assert m.contains_all_groups("x", []) == (None, [])


def test_refusal_detection():
    assert m.is_refusal("The available documents do not provide sufficient information to answer this.", True)
    assert m.is_refusal("anything", False) and not m.is_refusal("The limit is 5.", True)


def test_citation_validity():
    assert m.citation_validity("A [1] B [2]", [1, 2]) == {"has_citation": 1.0, "valid_citation_rate": 1.0}
    assert m.citation_validity("A [1] B [7]", [1, 2])["valid_citation_rate"] == 0.5
    assert m.citation_validity("No cites", [1]) == {"has_citation": 0.0, "valid_citation_rate": None}


def test_numeric_grounding_flags_invented_numbers():
    ctx = ["Claims above ₹5,000 need approval within 30 days."]
    ok = m.numeric_grounding("Claims above ₹5,000 need approval [1] within 30 days.", ctx)
    assert ok["rate"] == 1.0
    bad = m.numeric_grounding("Claims above ₹7,500 need approval within 30 days [1].", ctx)
    assert bad["ungrounded"] == ["7500"] and bad["rate"] == 0.5
    assert m.numeric_grounding("No numbers at all.", ctx)["rate"] is None


def test_percentiles_and_aggregate():
    assert m.percentile([10, 20, 30, 40, 50], 50) == 30 and m.percentile([], 95) is None
    results = [
        {"hit": 1.0, "rr": 1.0, "precision": 0.5, "retrieved_count": 4, "total_ms": 100, "should_refuse": None, "refused": False, "fact_recall": 1.0},
        {"hit": 0.0, "rr": 0.0, "precision": 0.0, "retrieved_count": 2, "total_ms": 300, "should_refuse": True, "refused": True},
        {"error": "boom"},
    ]
    agg = m.aggregate(results)
    assert agg["questions"] == 3 and agg["errors"] == 1 and agg["retrieval"]["hit_rate"] == 0.5
    assert agg["answer"]["out_of_scope_refused"] == 1.0 and agg["latency_ms"]["mean"] == 200


def test_question_file_is_valid_and_honest():
    qs = load_questions(Path(__file__).parent.parent / "evaluation" / "questions.json")
    assert len(qs) >= 8 and len({q["id"] for q in qs}) == len(qs)
    assert any(q.get("should_refuse") for q in qs)
    assert any(q["category"] == "comparison" for q in qs)
    assert any(q["category"] == "region" for q in qs)


def test_invalid_question_files_are_rejected(tmp_path):
    def write(data):
        p = tmp_path / "q.json"
        p.write_text(json.dumps(data))
        return p

    with pytest.raises(ValueError):
        load_questions(write({"questions": [{"id": "a"}]}))
    with pytest.raises(ValueError):
        load_questions(write({"questions": [{"id": "a", "question": "x"}, {"id": "a", "question": "y"}]}))
    with pytest.raises(ValueError):
        load_questions(write({"questions": [{"id": "a", "question": "x", "should_refuse": True, "expected": {"doc_codes": ["K"]}}]}))


def test_report_states_its_limits():
    report = {"generated_at": "t", "mode": "full", "environment": {"embedding": "e", "llm_model": "m", "chunk_config": "400/60/40", "top_k": 6, "similarity_cutoff": 0.25, "documents": 1, "chunks": 2},
              "aggregate": m.aggregate([{"hit": 1.0, "rr": 1.0, "precision": 1.0, "retrieved_count": 1, "total_ms": 5}]), "results": [{"id": "q1", "category": "c", "hit": 1.0}]}
    text = render_markdown(report)
    assert "Limits of this evaluation" in text and "string matching" in text
