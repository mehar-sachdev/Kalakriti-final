"""Metadata extraction.

Two sources are combined:

1. the *file system*   -> department, filename, type, checksum, stable id;
2. the *document body* -> many corporate documents open with a small
   "Document ID / Version / Status / Effective date / ..." table.  Those values
   are parsed so answers can name the version and status of what they cite.

The parser works both on Markdown tables (``| Document ID | KAL-FIN-POL-009 |``)
and on run-together text (``Document ID KAL-FIN-POL-010 Department Finance ...``),
because PDFs sometimes come out either way.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.models.documents import SourceDocument

# label as printed in documents -> normalised key
HEADER_LABELS: dict[str, str] = {
    "Document ID": "doc_code",
    # Kalakriti product/region/craft documents (see scripts/generate_documents.py)
    "Product ID": "product_id",
    "City": "city",
    "Craft Type": "craft_category",
    "Craft Category": "craft_category",
    "Region": "declared_department",
    "Cities Represented": "cities_represented",
    "Associated Regions": "associated_regions",
    "Catalogue Items": "catalogue_item_count",
    "Price (INR)": "price_inr",
    "Rating": "rating",
    "Availability": "availability",
    "Product URL": "product_url",
    "Data Status": "data_status",
    "Workbook Name": "workbook_name",
    "Related Source Document": "related_source_document",
    "Source Version": "source_version",
    "Document Type": "document_type",
    "Effective Date": "effective_date",
    "Review Date": "review_date",
    "Document Owner": "owner",
    "Approved By": "approved_by",
    "Classification": "classification",
    "Source Basis": "source_basis",
    "Department": "declared_department",
    "Version": "version",
    "Status": "status",
    "Owner": "owner",
}
# Labels that end a value but are not stored.
STOP_LABELS = ["Note", "Notes"]

# Lookarounds instead of \b: "_" counts as a word character, so "KAL-HR-XLSX-002A_Leave.xlsx" needs them.
DOC_CODE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,6}-[A-Z]{2,5}-[A-Z]{2,5}-\d{2,4}[A-Z]?(?![A-Za-z0-9])")
_LABEL_RE = re.compile(
    r"(?<![A-Za-z])("
    + "|".join(re.escape(l) for l in sorted([*HEADER_LABELS, *STOP_LABELS], key=len, reverse=True))
    + r")(?![A-Za-z])"
)
_SECTION_START_RE = re.compile(r"(?m)^(?:#{1,6}\s+)?\d{1,2}(?:\.\d{1,2})*[.)]?\s+[A-Z]")
_SHEET_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+Sheet:\s")
_FILENAME_PREFIX_RE = re.compile(
    r"^(?:[A-Z]{2,6}-[A-Z]{2,5}-[A-Z]{2,5}-\d{2,4}[A-Z]?|\d{1,3})[_\-\s]+"
)

_TYPE_KEYWORDS = [
    ("sop", "SOP"), ("standard operating", "SOP"), ("policy", "Policy"), ("guideline", "Guidelines"),
    ("agreement", "Agreement"), ("matrix", "Matrix"), ("checklist", "Checklist"), ("handbook", "Handbook"),
    ("knowledge base", "Knowledge Base"), ("terms and conditions", "Legal Terms"), ("code of conduct", "Code of Conduct"),
]


def title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = _FILENAME_PREFIX_RE.sub("", stem)
    title = re.sub(r"[_\s]+", " ", stem).strip()
    return title or Path(filename).stem


def infer_document_type(title: str) -> str:
    lowered = title.lower()
    for needle, label in _TYPE_KEYWORDS:
        if needle in lowered:
            return label
    return "Document"


_EMPHASIS_RE = re.compile(r"\*\*(.*?)\*\*|__(.*?)__|(?<!\w)\*(.*?)\*(?!\w)")


def _strip_emphasis(text: str) -> str:
    """Unwrap Markdown bold/italic (Docling renders a bolded header cell as ``**Label**``);
    without this, the closing/opening ``**`` around adjacent cells leaks into extracted values."""
    return _EMPHASIS_RE.sub(lambda m: next(g for g in m.groups() if g is not None), text)


def _header_region(markdown: str, limit: int = 4000) -> str:
    region = _strip_emphasis(markdown[:limit])
    cuts: list[int] = []
    match = _SECTION_START_RE.search(region, 1)
    if match:
        cuts.append(match.start())
    sheets = list(_SHEET_HEADING_RE.finditer(region))
    if len(sheets) >= 2:  # workbooks: the first sheet is usually the metadata sheet
        cuts.append(sheets[1].start())
    return region[: min(cuts)] if cuts else region


_SEPARATOR_RE = re.compile(r"\|?\s*:?-+:?\s*(?=\||$|\n)")


def _clean_value(raw: str) -> str:
    # A table's first row is its header, so a "|---|---|" separator can directly follow the value.
    value = _SEPARATOR_RE.sub(" ", raw)
    value = re.sub(r"\s*\|\s*", " ", value)
    value = value.replace("\\", "")
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n|:,;")
    return value


_ALL_LABELS = {**{k: v for k, v in HEADER_LABELS.items()}}
_TABLE_ROW_SEP_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def _split_table_row(line: str) -> list[str]:
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") else inner
    return [c.strip() for c in re.split(r"(?<!\\)\|", inner)]


def _from_table_rows(region: str) -> dict[str, str]:
    """Row-scoped extraction: each ``| Label | Value |`` line is self-contained, so a row whose
    label is not one we recognise can never swallow the next row's content (unlike scanning
    label-match to label-match across the whole block, which breaks as soon as any row in
    between is for an unmapped field)."""
    found: dict[str, str] = {}
    for line in region.split("\n"):
        if not line.lstrip().startswith("|") or _TABLE_ROW_SEP_RE.match(line):
            continue
        cells = _split_table_row(line)
        if len(cells) != 2:
            continue
        label, value = cells[0].strip(), _clean_value(cells[1])
        key = _ALL_LABELS.get(label)
        if key and value and len(value) <= 140:
            found.setdefault(key, value)
    return found


def _from_inline_text(region: str) -> dict[str, str]:
    """Fallback for headers written as run-together text (some PDFs), scanning from one
    recognised label to the next."""
    matches = list(_LABEL_RE.finditer(region))
    found: dict[str, str] = {}
    for index, match in enumerate(matches):
        label = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(region)
        raw = region[match.end():end]
        if index + 1 == len(matches):
            raw = re.split(r"\n\s*\n", raw.lstrip("\n"), maxsplit=1)[0]
        key = HEADER_LABELS.get(label)
        if key is None:
            continue
        value = _clean_value(raw)
        if not value or len(value) > 140:
            continue
        found.setdefault(key, value)
    return found


def extract_header_metadata(markdown: str) -> dict[str, str]:
    """Parse the 'Document ID / Version / ...' block found at the top of many documents."""
    region = _header_region(markdown)
    from_tables = _from_table_rows(region)
    if from_tables:
        return from_tables
    return _from_inline_text(region)


def extract_doc_codes(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for code in DOC_CODE_RE.findall(text):
        seen.setdefault(code, None)
    return list(seen)


def build_document_metadata(source: SourceDocument, markdown: str) -> dict[str, Any]:
    """Flat metadata dictionary for one document (used by the manifest, registry and nodes)."""
    header = extract_header_metadata(markdown)
    title = header.get("workbook_name") or title_from_filename(source.filename)

    doc_code = header.get("doc_code")
    if not doc_code or not DOC_CODE_RE.fullmatch(doc_code):
        match = DOC_CODE_RE.search(markdown[:3000]) or DOC_CODE_RE.search(source.filename)
        doc_code = match.group(0) if match else None

    related = header.get("related_source_document")
    related_code = None
    if related:
        m = DOC_CODE_RE.search(related)
        related_code = m.group(0) if m else None

    document_type = header.get("document_type") or infer_document_type(title)

    metadata: dict[str, Any] = {
        "document_id": source.document_id,
        "doc_code": doc_code,
        "title": title,
        "department": source.department_name,
        "department_slug": source.department_slug,
        "declared_department": header.get("declared_department"),
        "file_type": source.file_type,
        "source_filename": source.filename,
        "source_path": source.relative_path,
        "document_type": document_type,
        "version": header.get("version") or header.get("source_version"),
        "status": header.get("status"),
        "effective_date": header.get("effective_date"),
        "review_date": header.get("review_date"),
        "owner": header.get("owner"),
        "approved_by": header.get("approved_by"),
        "classification": header.get("classification"),
        "source_basis": header.get("source_basis"),
        "related_source_document": related,
        "related_source_code": related_code,
        # Kalakriti product/region/craft documents (see scripts/generate_documents.py)
        "product_id": header.get("product_id"),
        "city": header.get("city"),
        "craft_category": header.get("craft_category"),
        "product_url": header.get("product_url"),
        "price_inr": header.get("price_inr"),
        "rating": header.get("rating"),
        "availability": header.get("availability"),
    }
    return {k: v for k, v in metadata.items() if v not in (None, "")}


def cross_references(markdown: str, own_code: str | None) -> list[str]:
    return [c for c in extract_doc_codes(markdown) if c != own_code]
