from backend.ingestion.discovery import discover_documents
from backend.ingestion.markdown_utils import (clean_markdown, promote_numbered_headings, read_processed_markdown,
                                              write_processed_markdown, find_encoding_problems)
from backend.ingestion.metadata import (DOC_CODE_RE, build_document_metadata, cross_references, extract_doc_codes,
                                        extract_header_metadata, infer_document_type, title_from_filename)

TABLE = """| Document ID | KAL-FIN-POL-010 |
|---|---|
| Department | Finance |
| Version | 1.1 |
| Status | Active |
| Effective Date | 01-Aug-2026 |
| Document Owner | Head of Finance |
| Classification | Internal — Restricted |

## 1. Purpose
Body text with Status mentioned here that must not be parsed.
"""
INLINE = "Document ID KAL-HR-POL-002 Department HR & Administration Document Type Policy Version 2.0 Status Active Effective Date 01-Aug-2026 Classification Internal\n\n1. Purpose\nText."


def test_header_from_markdown_table():
    h = extract_header_metadata(TABLE)
    assert h["doc_code"] == "KAL-FIN-POL-010" and h["declared_department"] == "Finance" and h["version"] == "1.1"
    assert h["status"] == "Active" and h["owner"] == "Head of Finance" and h["classification"] == "Internal — Restricted"


def test_header_from_run_together_text():
    h = extract_header_metadata(INLINE)
    assert h["doc_code"] == "KAL-HR-POL-002" and h["declared_department"] == "HR & Administration"
    assert h["document_type"] == "Policy" and h["version"] == "2.0" and h["classification"] == "Internal"


def test_body_text_after_first_section_is_not_parsed_as_header():
    assert "must not" not in " ".join(extract_header_metadata(TABLE).values())


def test_xlsx_metadata_sheet_only_and_note_label_stops_value():
    md = "## Sheet: Metadata\n\n| Document ID | KAL-HR-XLSX-002A |\n|---|---|\n| Related Source Document | KAL-HR-POL-002 — Leave Policy |\n| Classification | Internal |\n| Note | synthetic |\n\n## Sheet: Leave Types\n\n| Status | Days |\n|---|---|\n| Active | 10 |\n"
    h = extract_header_metadata(md)
    assert h["related_source_document"].startswith("KAL-HR-POL-002") and h["classification"] == "Internal"
    assert "status" not in h  # the 'Status' column of the second sheet is not header metadata


def test_doc_code_regex_and_extraction():
    text = "See KAL-FIN-POL-008, KAL-HR-XLSX-002A and KAL-FIN-POL-008 again; not KAL-1-2."
    assert extract_doc_codes(text) == ["KAL-FIN-POL-008", "KAL-HR-XLSX-002A"]
    assert DOC_CODE_RE.fullmatch("KAL-LEG-SOP-030")
    assert cross_references(text, "KAL-HR-XLSX-002A") == ["KAL-FIN-POL-008"]


def test_title_and_type_from_filename():
    assert title_from_filename("09_Expense_and_Reimbursement_Policy.docx") == "Expense and Reimbursement Policy"
    assert title_from_filename("KAL-FIN-XLSX-010A_Financial_Approval_Matrix.xlsx") == "Financial Approval Matrix"
    assert infer_document_type("Returns SOP") == "SOP" and infer_document_type("Leave Matrix") == "Matrix"
    assert infer_document_type("Something else") == "Document"


def test_build_metadata_keeps_folder_department_and_declared_department(corpus):
    doc = next(d for d in discover_documents(corpus).documents if d.filename.endswith("xlsx"))
    md = "## Sheet: Metadata\n\n| Document ID | TST-SAL-XLSX-002A |\n|---|---|\n| Department | Sales |\n| Related Source Document | TST-SAL-POL-002 — X |\n"
    meta = build_document_metadata(doc, md)
    assert meta["department"] == "Sales & Customer" and meta["declared_department"] == "Sales"
    assert meta["related_source_code"] == "TST-SAL-POL-002" and meta["document_type"] == "Matrix"


def test_build_metadata_falls_back_to_code_in_filename(corpus):
    doc = next(d for d in discover_documents(corpus).documents if d.filename.startswith("TST-SAL"))
    assert build_document_metadata(doc, "no header at all")["doc_code"] == "TST-SAL-XLSX-002A"


# ---- markdown utils -------------------------------------------------------------------------
def test_clean_markdown_normalises_whitespace_and_images():
    out, _ = clean_markdown("a\u00a0b\r\n\r\n\r\n\r\n<!-- image -->\nc  \n", promote_headings=False)
    assert out == "a b\n\nc\n"


def test_numbered_paragraphs_become_headings_preserving_numbering():
    md = "Title\n\n1. Purpose\n\nText.\n\n5.1 Business Travel\n\nMore.\n"
    out, n = promote_numbered_headings(md)
    assert n == 2 and "## 1. Purpose" in out and "### 5.1 Business Travel" in out


def test_promotion_skipped_when_document_has_real_headings():
    md = "## A\n\n## B\n\n## C\n\n1. Something\n"
    assert promote_numbered_headings(md) == (md, 0)


def test_promotion_ignores_list_items_and_sentences():
    md = "Intro\n\n1. First item that ends with a period.\n2. Second item\n\nNormal text.\n"
    assert promote_numbered_headings(md)[1] == 0


def test_processed_file_roundtrip(tmp_path):
    p = tmp_path / "x" / "doc.md"
    write_processed_markdown(p, "# Body\n\ntext ₹5,000", {"document_id": "d1", "page_count": 3, "title": 'Quote "q"'})
    meta, body = read_processed_markdown(p)
    assert meta == {"document_id": "d1", "page_count": 3, "title": 'Quote "q"'} and body == "# Body\n\ntext ₹5,000"


def test_encoding_problem_detection():
    assert find_encoding_problems("price â‚¹500 and bad \ufffd char")["mojibake"] == 1
    assert find_encoding_problems("price ₹500 clean") == {"replacement_chars": 0, "mojibake": 0, "control_chars": 0}
