import pytest

pytest.importorskip("docling")

from backend.exceptions import ParsingError
from backend.ingestion.discovery import discover_documents
from backend.ingestion.markdown_utils import PAGE_MARKER_RE
from backend.ingestion.parser import ParserRegistry, PdfiumFallbackParser, TextParser
from tests.helpers import make_docx, make_pdf, make_xlsx


def _source(corpus, suffix):
    return next(d for d in discover_documents(corpus).documents if d.filename.endswith(suffix))


@pytest.mark.docling
def test_docx_becomes_markdown_with_tables_and_currency(corpus, offline_registry):
    parsed = offline_registry.parse(_source(corpus, "Policy.docx"))
    assert parsed.parser == "docling"
    assert "| Category" in parsed.markdown and "₹1,200/day" in parsed.markdown
    assert "1,00,000" in parsed.markdown  # Indian digit grouping survives
    assert "Travel & lodging" in parsed.markdown and "&amp;" not in parsed.markdown  # HTML escaping is off
    assert "snake_case_code" in parsed.markdown and "\\_" not in parsed.markdown  # underscores are not escaped


@pytest.mark.docling
def test_xlsx_sheet_names_are_recovered_as_headings(corpus, offline_registry):
    parsed = offline_registry.parse(_source(corpus, ".xlsx"))
    assert parsed.sheets == ["Metadata", "Approval Rules"]
    assert "## Sheet: Approval Rules" in parsed.markdown and "Director" in parsed.markdown


def test_text_and_markdown_pass_through(corpus, settings):
    reg = ParserRegistry(settings)
    assert "reimbursement claims" in reg.parse(_source(corpus, "notes.txt")).markdown
    assert reg.parse(_source(corpus, "vendor_terms.md")).markdown.startswith("# Vendor Terms")


def test_text_parser_handles_non_utf8(tmp_path, corpus):
    f = corpus / "Finance" / "latin.txt"
    f.write_bytes("Prix: 5\u20ac".encode("cp1252"))
    parsed = TextParser().parse(_source(corpus, "latin.txt"))
    assert "5" in parsed.markdown and parsed.warnings


def test_pdf_fallback_emits_page_markers_and_flags_low_fidelity(corpus):
    parsed = PdfiumFallbackParser().parse(_source(corpus, ".pdf"))
    assert [int(n) for n in PAGE_MARKER_RE.findall(parsed.markdown)] == [1, 2]
    assert "14 days" in parsed.markdown and parsed.page_count == 2
    assert any("FALLBACK" in w for w in parsed.warnings)


def test_pdf_falls_back_only_when_enabled(corpus, make_settings, monkeypatch):
    from backend.ingestion.parser import DoclingParser

    def boom(self, source):
        raise ParsingError("layout model unavailable")

    monkeypatch.setattr(DoclingParser, "parse", boom)
    pdf = _source(corpus, ".pdf")
    ok = ParserRegistry(make_settings(enable_parser_fallback=True)).parse(pdf)
    assert ok.parser == "pypdfium2-fallback" and ok.warnings[0].startswith("PRIMARY_PARSER_FAILED")
    with pytest.raises(ParsingError):
        ParserRegistry(make_settings(enable_parser_fallback=False)).parse(pdf)


@pytest.mark.docling
def test_corrupted_docx_raises_parsing_error(corpus, settings):
    with pytest.raises(ParsingError):
        ParserRegistry(settings).parse(_source(corpus, "broken.docx"))


def test_unregistered_type_raises(corpus, settings):
    from dataclasses import replace

    src = replace(_source(corpus, "notes.txt"), file_type="dwg")
    with pytest.raises(ParsingError):
        ParserRegistry(settings).parse(src)


@pytest.mark.docling
@pytest.mark.skipif(not __import__("os").environ.get("RUN_DOCLING_PDF_TESTS"), reason="set RUN_DOCLING_PDF_TESTS=1 (downloads Docling layout models)")
def test_real_docling_pdf_conversion(corpus, settings):
    parsed = ParserRegistry(settings).parse(_source(corpus, ".pdf"))
    assert parsed.parser == "docling" and "14 days" in parsed.markdown
    assert [int(n) for n in PAGE_MARKER_RE.findall(parsed.markdown)] == [1, 2]
