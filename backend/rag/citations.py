"""Turning retrieved nodes into citations, and citations back into text."""
from __future__ import annotations

import re

from llama_index.core.schema import NodeWithScore

from backend.models.schemas import SourceRef

_CITE_RE = re.compile(r"\[(\d{1,2})\]")


def extract_cited_ids(answer: str) -> set[int]:
    """Excerpt numbers the model referred to, e.g. 'limit is ₹5,000 [1][3]' -> {1, 3}."""
    return {int(m) for m in _CITE_RE.findall(answer)}


def make_excerpt(text: str, limit: int | None = 420) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if limit is None or len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + " …"


def node_to_source(citation_id: int, item: NodeWithScore, *, used: bool = True, excerpt_chars: int | None = 420) -> SourceRef:
    meta = item.node.metadata
    page = meta.get("page_number")
    return SourceRef(
        citation_id=citation_id,
        document_id=meta.get("document_id", ""),
        document=meta.get("source_path") or meta.get("source_filename", "unknown"),
        title=meta.get("title"),
        doc_code=meta.get("doc_code"),
        department=meta.get("department", "Unknown"),
        department_slug=meta.get("department_slug", ""),
        file_type=meta.get("file_type"),
        page=int(page) if page is not None else None,
        section=meta.get("section_path"),
        sheet=meta.get("sheet_name"),
        version=str(meta["version"]) if meta.get("version") is not None else None,
        status=meta.get("status"),
        classification=meta.get("classification"),
        score=round(float(item.score), 4) if item.score is not None else None,
        excerpt=make_excerpt(item.node.get_content(), excerpt_chars),
        used_in_answer=used,
    )


def location_label(source: SourceRef) -> str:
    """'Page 4', 'Sheet: Entitlements' or the section, whichever the source supports."""
    if source.page:
        return f"Page {source.page}"
    if source.sheet:
        return f"Sheet: {source.sheet}"
    if source.section:
        return f"Section: {source.section}"
    return ""


def render_sources_text(sources: list[SourceRef]) -> str:
    """Plain-text citation block for the CLI:  'Source: Finance/x.pdf / Page: 4'."""
    if not sources:
        return "Source: none (no relevant documents were retrieved)"
    lines: list[str] = []
    for s in sources:
        flag = "" if s.used_in_answer else "  (retrieved, not cited)"
        lines.append(f"[{s.citation_id}] Source: {s.document}{flag}")
        if s.page:
            lines.append(f"     Page: {s.page}")
        if s.sheet:
            lines.append(f"     Sheet: {s.sheet}")
        if s.section:
            lines.append(f"     Section: {s.section}")
        detail = " ".join(filter(None, [s.doc_code, f"v{s.version}" if s.version else None, f"({s.status})" if s.status else None]))
        lines.append(f"     Department: {s.department}" + (f"   Document: {detail}" if detail else "") +
                     (f"   Score: {s.score:.2f}" if s.score is not None else ""))
    return "\n".join(lines)
