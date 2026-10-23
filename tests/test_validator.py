import pytest

from backend.ingestion.discovery import discover_documents
from backend.ingestion.validator import (Reference, find_tables, number_set, table_problems, validate_markdown, word_set)
from backend.models.documents import SourceDocument
from pathlib import Path


def src(ft="docx"):
    return SourceDocument(Path("x." + ft), "Dept/x." + ft, "Dept", "dept", ft, 1, "abc", "dept__x-" + ft)


GOOD = "# Policy\n\nThe limit is ₹1,00,000 per claim within 30 days.\n\n| Category | Limit |\n|---|---|\n| Meals | ₹1,200 |\n"


def ref(text, **kw):
    return Reference(text, **kw)


def test_tokenizers():
    assert "limit" in word_set("The Limit is 5") and "is" not in word_set("The Limit is 5")
    assert number_set("₹1,00,000 and 12.50 and 3.0") == {"100000", "12.5", "3"}


def test_clean_document_passes():
    r = validate_markdown(GOOD, src(), reference=ref("Policy limit ₹1,00,000 claim within 30 days Category Limit Meals ₹1,200", tables=1))
    assert r.status == "ok" and r.stats["word_recall"] == 1.0 and r.stats["number_recall"] == 1.0


def test_dropped_table_content_is_detected_by_number_recall():
    truncated = "# Policy\n\nThe limit is ₹1,00,000 per claim.\n"
    r = validate_markdown(truncated, src(), reference=ref("Policy limit ₹1,00,000 claim Meals ₹1,200 Travel ₹850 Hotel ₹5,500 Category", tables=1))
    codes = {i.code for i in r.issues}
    assert r.status in {"warning", "error"} and ("NUMBER_RECALL" in codes or "LOW_NUMBER_RECALL" in codes)
    assert "TABLE_COUNT" in codes and "1200" in r.stats["missing_numbers_sample"]


def test_large_content_loss_is_an_error():
    r = validate_markdown("# T\n\nOnly a few words survive here in this output text.\n", src(),
                          reference=ref(" ".join(f"uniqueword{chr(97 + i % 26)}{chr(97 + i // 26)}x" for i in range(200)) + " survive here few words"))
    assert r.status == "error" and "LOW_TEXT_RECALL" in {i.code for i in r.issues}


def test_empty_output_is_an_error():
    assert validate_markdown("  \n", src(), reference=ref("something")).status == "error"


def test_encoding_damage_is_flagged():
    r = validate_markdown("# T\n\nPrice â‚¹500 and bad \ufffd char in a long enough line.\n", src(), reference=ref(""))
    assert {"ENCODING_MOJIBAKE", "ENCODING_REPLACEMENT_CHARS"} <= {i.code for i in r.issues}


def test_malformed_tables():
    assert table_problems(["| a | b |", "|---|---|", "| 1 | 2 |"]) == []
    assert "missing header separator row" in table_problems(["| a | b |", "| 1 | 2 |"])[0]
    assert any("inconsistent" in p for p in table_problems(["| a | b |", "|---|---|", "| 1 | 2 | 3 |"]))
    assert table_problems(["| a | b |", "| :-: | :-: |", "| 1 | 2 |"]) == []  # alignment syntax is valid
    assert len(find_tables(GOOD + "\ntext\n\n| x |\n|---|\n| y |\n")) == 2


def test_missing_sheet_and_page_checks():
    md = "## Sheet: Metadata\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    r = validate_markdown(md, src("xlsx"), reference=ref("a b 1 2", sheets=["Metadata", "Rules"]))
    assert "MISSING_SHEETS" in {i.code for i in r.issues}
    pdf = "<!-- page: 1 -->\n\nFirst page has plenty of extractable text here.\n\n<!-- page: 2 -->\n\n\n"
    r = validate_markdown(pdf, src("pdf"), reference=ref("First page plenty extractable text here", pages=2))
    assert "EMPTY_PAGE" in {i.code for i in r.issues}


def test_no_headings_warning_only_for_long_docs():
    long_text = "word " * 400
    assert "NO_HEADINGS" in {i.code for i in validate_markdown(long_text, src(), reference=ref(long_text)).issues}
    assert "NO_HEADINGS" not in {i.code for i in validate_markdown("short text here that is fine.\n", src(), reference=ref("")).issues}


def test_independent_reference_extractors_work(corpus):
    from backend.ingestion.validator import extract_reference

    docs = {d.filename: d for d in discover_documents(corpus).documents}
    docx_ref = extract_reference(docs["09_Fixture_Expense_Policy.docx"])
    assert "₹1,200/day" in docx_ref.text and docx_ref.tables == 2
    assert extract_reference(docs["TST-SAL-XLSX-002A_Fixture_Matrix.xlsx"]).sheets == ["Metadata", "Approval Rules"]
    pdf_ref = extract_reference(docs["12_Fixture_Return_Policy.pdf"])
    assert "14 days" in pdf_ref.text and pdf_ref.pages == 2
