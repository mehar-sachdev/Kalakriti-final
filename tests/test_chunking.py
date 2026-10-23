import pytest

from backend.rag.chunking import MarkdownChunker, estimate_tokens, parse_blocks

META = {"document_id": "fin__doc-pdf", "title": "Doc", "department": "Finance", "department_slug": "finance", "doc_code": "X-1", "file_type": "pdf"}
PROSE = " ".join(f"Sentence number {i} explains a travel reimbursement rule with amount ₹{i * 100}." for i in range(60))
TABLE = "\n".join(["| Claim Amount | Approver |", "|---|---|"] + [f"| ₹{i * 1000 + 1} – ₹{(i + 1) * 1000} | Approver number {i} for department heads |" for i in range(60)])
DOC = f"""<!-- page: 1 -->

# Policy

| Document ID | X-1 |
|---|---|
| Version | 1.1 |

## 1. Purpose

Short purpose text about expense claims and how they are filed by staff members.

## 5. Employee Expenses

### 5.1 Business Travel

{PROSE}

<!-- page: 2 -->

### 5.2 Approval matrix

{TABLE}

## 13. Related Documents

- Payment Policy — KAL-FIN-POL-006
- Records SOP — KAL-LEG-SOP-030
"""


@pytest.fixture(scope="module")
def nodes():
    return MarkdownChunker(400, 60, 40).chunk(DOC, META)


def test_chunks_respect_size_limit(nodes):
    assert all(estimate_tokens(n.text) <= 420 for n in nodes)
    assert len(nodes) >= 8


def test_no_empty_or_heading_only_chunks(nodes):
    for n in nodes:
        body = [l for l in n.text.split("\n") if l.strip() and not l.startswith("#")]
        assert body, n.node_id


def test_chunks_do_not_cross_sections(nodes):
    for n in nodes:
        headings = [l for l in n.text.split("\n") if l.startswith("#")]
        assert len(headings) <= 2
    travel = [n for n in nodes if n.metadata.get("section") == "5.1 Business Travel"]
    assert travel and all("Approver number" not in n.text for n in travel)


def test_section_path_and_pages_are_tracked(nodes):
    travel = next(n for n in nodes if n.metadata.get("section") == "5.1 Business Travel")
    assert travel.metadata["section_path"] == "Policy > 5. Employee Expenses > 5.1 Business Travel" and travel.metadata["page_number"] == 1
    matrix = [n for n in nodes if n.metadata.get("section") == "5.2 Approval matrix"]
    assert matrix and all(n.metadata["page_number"] == 2 for n in matrix)


def test_oversized_table_splits_by_row_and_repeats_header(nodes):
    pieces = [n for n in nodes if n.metadata.get("section") == "5.2 Approval matrix"]
    assert len(pieces) >= 3
    for n in pieces:
        assert "| Claim Amount | Approver |" in n.text and "|---|---|" in n.text
        assert all(l.count("|") == 3 for l in n.text.split("\n") if l.startswith("|"))
    rows = sum(1 for n in pieces for l in n.text.split("\n") if l.startswith("| ₹"))
    assert rows == 60  # no row lost, none duplicated


def test_long_prose_is_split_on_sentences_with_overlap():
    doc = f"## Sec\n\n{PROSE}\n"
    ns = MarkdownChunker(200, 40, 20).chunk(doc, META)
    assert len(ns) > 2
    assert all(n.text.rstrip().endswith(".") or n.text.rstrip().endswith("0.") for n in ns)  # ends at a sentence boundary
    import re

    for first, second in zip(ns, ns[1:]):
        last_sentence = re.findall(r"Sentence number \d+", first.text)[-1]
        assert last_sentence in second.text, "consecutive chunks must overlap by at least one sentence"
    assert sum(len(n.text) for n in ns) >= len(PROSE) * 0.98  # nothing dropped


def test_excel_sheets_never_merge():
    md = "## Sheet: Leave Types\n\n| Type | Days |\n|---|---|\n| Sick | 10 |\n\n## Sheet: Approval Rules\n\n| Duration | Approver |\n|---|---|\n| 1-3 days | Manager |\n"
    ns = MarkdownChunker().chunk(md, {"document_id": "hr__m-xlsx"})
    assert [n.metadata["sheet_name"] for n in ns] == ["Leave Types", "Approval Rules"]


def test_small_fragments_merge_forward_within_a_sheet():
    md = "## Notes\n\nTiny one.\n\n## More\n\nAlso tiny two.\n\n## Big\n\n" + PROSE[:900] + "\n"
    ns = MarkdownChunker(400, 60, 60).chunk(md, {"document_id": "d"})
    assert len(ns) < 3 and any("Tiny one" in n.text and "Also tiny two" in n.text for n in ns)


def test_ids_are_deterministic_and_metadata_is_flat_and_complete(nodes):
    again = MarkdownChunker(400, 60, 40).chunk(DOC, META)
    assert [n.node_id for n in nodes] == [n.node_id for n in again] and nodes[0].node_id == "fin__doc-pdf::0000"
    for n in nodes:
        assert all(isinstance(v, (str, int, float)) for v in n.metadata.values())
        assert n.metadata["department_slug"] == "finance" and n.metadata["chunk_count"] == len(nodes)
        assert n.ref_doc_id == "fin__doc-pdf"


def test_embedding_text_contains_context_but_llm_text_is_clean(nodes):
    from llama_index.core.schema import MetadataMode

    n = nodes[3]
    embed_text = n.get_content(metadata_mode=MetadataMode.EMBED)
    assert "department: Finance" in embed_text and "section_path:" in embed_text and "chunk_index" not in embed_text
    assert n.get_content(metadata_mode=MetadataMode.LLM) == n.text


def test_parse_blocks_types():
    kinds = [b.kind for b in parse_blocks("# H\n\npara\n\n- a\n- b\n\n| x |\n|---|\n| 1 |\n")]
    assert kinds == ["heading", "prose", "list", "table"]


def test_invalid_overlap_rejected():
    with pytest.raises(ValueError):
        MarkdownChunker(100, 100, 10)


def test_empty_document_yields_no_chunks():
    assert MarkdownChunker().chunk("\n\n", {"document_id": "d"}) == []
