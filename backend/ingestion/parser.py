"""Document -> Markdown conversion.

Docling is the primary parser (assignment requirement).  Additions to make the
output *faithful*:

* PDFs are exported page by page and every page is preceded by a
  ``<!-- page: N -->`` marker, so chunks can cite page numbers.
* Excel workbooks: Docling models every sheet as a named group, but its
  Markdown export drops the sheet names.  We re-insert ``## Sheet: <name>``
  headings, because the sheet name ("Approval Rules", "Entitlements") carries
  meaning.
* Docling's default Markdown escapes ``_`` and ``&``; both are switched off so the
  text stays readable and searchable.

Other formats (``.txt``/``.md``) are passed through.  An optional low-fidelity PDF
fallback (pdfium text) can be enabled with ``ENABLE_PARSER_FALLBACK=true``; when
it is used the result is flagged in the manifest and the parsing report.
"""
from __future__ import annotations

import logging
from importlib import metadata as importlib_metadata
from typing import Protocol

from backend.config import Settings
from backend.exceptions import ParsingError
from backend.ingestion.markdown_utils import PAGE_MARKER_FMT, SHEET_HEADING_PREFIX
from backend.models.documents import ParsedDocument, SourceDocument

logger = logging.getLogger(__name__)

DOCLING_FORMATS = {"pdf", "docx", "xlsx", "xls", "csv"}
TEXT_FORMATS = {"txt", "md"}


class Parser(Protocol):
    name: str

    def parse(self, source: SourceDocument) -> ParsedDocument: ...


def docling_version() -> str:
    for dist in ("docling", "docling-slim"):
        try:
            return importlib_metadata.version(dist)
        except importlib_metadata.PackageNotFoundError:
            continue
    try:  # pragma: no cover
        import docling  # type: ignore

        return getattr(docling, "__version__", "unknown")
    except ImportError:
        return "not-installed"


# ---------------------------------------------------------------------------- Docling
class DoclingParser:
    name = "docling"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._converter = None

    @property
    def version(self) -> str:
        return docling_version()

    def _get_converter(self):
        if self._converter is None:
            try:
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions
                from docling.document_converter import DocumentConverter, PdfFormatOption
            except ImportError as exc:
                raise ParsingError(
                    "Docling is not installed in this Python environment.",
                    hint="Activate your virtualenv and run: pip install docling",
                ) from exc

            pdf_options = PdfPipelineOptions()
            pdf_options.do_ocr = self.settings.docling_do_ocr
            pdf_options.do_table_structure = self.settings.docling_table_structure
            pdf_options.document_timeout = self.settings.docling_document_timeout_seconds
            self._converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}
            )
            logger.info(
                "Docling %s ready (ocr=%s, table_structure=%s)",
                self.version, self.settings.docling_do_ocr, self.settings.docling_table_structure,
            )
        return self._converter

    # -- helpers ------------------------------------------------------------------
    @staticmethod
    def _export(dl_doc, **kwargs) -> str:
        return dl_doc.export_to_markdown(
            escape_underscores=False, escape_html=False, image_placeholder="", **kwargs
        ).strip()

    @staticmethod
    def _sheet_names_by_page(dl_doc) -> dict[int, str]:
        """Map Docling 'page' numbers of a workbook to their sheet names."""
        mapping: dict[int, str] = {}
        for group in getattr(dl_doc, "groups", []) or []:
            label = getattr(group.label, "value", str(group.label))
            if label != "sheet":
                continue
            for ref in group.children:
                try:
                    item = ref.resolve(dl_doc)
                except Exception:  # noqa: BLE001
                    continue
                for prov in getattr(item, "prov", None) or []:
                    mapping.setdefault(prov.page_no, group.name)
        return mapping

    def parse(self, source: SourceDocument) -> ParsedDocument:
        converter = self._get_converter()
        try:
            result = converter.convert(str(source.path), raises_on_error=False)
        except Exception as exc:  # noqa: BLE001 - library raises many types
            raise ParsingError(f"Docling could not open the file: {exc}") from exc

        status = getattr(result.status, "name", str(result.status))
        errors = [getattr(e, "error_message", str(e)) for e in (getattr(result, "errors", None) or [])]
        if status not in {"SUCCESS", "PARTIAL_SUCCESS"}:
            detail = "; ".join(errors[:3]) or "no error detail"
            raise ParsingError(f"Docling conversion failed ({status}): {detail}")

        warnings: list[str] = []
        if status == "PARTIAL_SUCCESS":
            warnings.append("PARTIAL_SUCCESS: Docling skipped some content: " + "; ".join(errors[:3]))

        dl_doc = result.document
        page_count = dl_doc.num_pages() or None
        sheets: list[str] = []

        if source.file_type == "pdf" and page_count:
            parts = []
            for page_no in sorted(dl_doc.pages):
                body = self._export(dl_doc, page_no=page_no)
                parts.append(f"{PAGE_MARKER_FMT.format(n=page_no)}\n\n{body}".strip())
            markdown = "\n\n".join(parts)
        elif source.file_type in {"xlsx", "xls"}:
            sheet_by_page = self._sheet_names_by_page(dl_doc)
            if sheet_by_page:
                parts = []
                for page_no in sorted(sheet_by_page):
                    body = self._export(dl_doc, page_no=page_no)
                    if not body:
                        warnings.append(f"Sheet '{sheet_by_page[page_no]}' produced no content.")
                        continue
                    sheets.append(sheet_by_page[page_no])
                    parts.append(f"## {SHEET_HEADING_PREFIX}{sheet_by_page[page_no]}\n\n{body}")
                markdown = "\n\n".join(parts)
            else:
                markdown = self._export(dl_doc)
                warnings.append("Sheet names could not be recovered from the Docling result.")
            page_count = len(sheets) or page_count  # sheets play the role of pages
        else:
            markdown = self._export(dl_doc)
            if source.file_type == "docx":
                page_count = None  # Word files are not paginated without rendering

        return ParsedDocument(
            markdown=markdown,
            parser=self.name,
            parser_version=self.version,
            page_count=page_count,
            warnings=warnings,
            sheets=sheets,
        )


# ---------------------------------------------------------------------------- plain text
class TextParser:
    name = "builtin-text"

    def parse(self, source: SourceDocument) -> ParsedDocument:
        raw = source.path.read_bytes()
        warnings: list[str] = []
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
            warnings.append("File is not UTF-8; decoded as Windows-1252.")
        return ParsedDocument(markdown=text, parser=self.name, parser_version="1", warnings=warnings)


# ---------------------------------------------------------------------------- PDF fallback
class PdfiumFallbackParser:
    """Text-only extraction with pdfium.  No headings, no table structure."""

    name = "pypdfium2-fallback"

    def parse(self, source: SourceDocument) -> ParsedDocument:
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:  # pragma: no cover
            raise ParsingError("pypdfium2 is not installed; fallback parser unavailable.") from exc
        try:
            pdf = pdfium.PdfDocument(str(source.path))
        except Exception as exc:  # noqa: BLE001
            raise ParsingError(f"PDF could not be opened (corrupted or encrypted?): {exc}") from exc
        parts = []
        for index in range(len(pdf)):
            text = pdf[index].get_textpage().get_text_range().replace("\r\n", "\n").strip()
            parts.append(f"{PAGE_MARKER_FMT.format(n=index + 1)}\n\n{text}".strip())
        version = getattr(pdfium, "PYPDFIUM_INFO", None)
        return ParsedDocument(
            markdown="\n\n".join(parts),
            parser=self.name,
            parser_version=str(getattr(version, "version", "")) or "unknown",
            page_count=len(pdf),
            warnings=["FALLBACK_PARSER: headings and tables were not reconstructed (lower fidelity)."],
        )


# ---------------------------------------------------------------------------- registry
class ParserRegistry:
    """Maps file types to parsers.  Register more here to support new formats."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.docling = DoclingParser(settings)
        self.text = TextParser()
        self.fallback = PdfiumFallbackParser()

    @property
    def docling_version(self) -> str:
        return self.docling.version

    def parse(self, source: SourceDocument) -> ParsedDocument:
        if source.file_type in TEXT_FORMATS:
            return self.text.parse(source)
        if source.file_type not in DOCLING_FORMATS:
            raise ParsingError(f"No parser registered for '.{source.file_type}' files.")
        try:
            return self.docling.parse(source)
        except ParsingError as primary_error:
            if source.file_type == "pdf" and self.settings.enable_parser_fallback:
                logger.warning("Docling failed on %s (%s); using fallback parser.", source.relative_path, primary_error.message)
                parsed = self.fallback.parse(source)
                parsed.warnings.insert(0, f"PRIMARY_PARSER_FAILED: {primary_error.message}")
                return parsed
            raise
