"""Structure-aware chunking of Markdown into LlamaIndex ``TextNode`` objects.

Strategy (rationale in docs/rag_pipeline.md):

1. Parse the Markdown into *blocks* (heading, paragraph, list, table) while tracking
   the current heading path and the current page.
2. A chunk never crosses a section boundary: text under "5.1 Business Travel" is not
   mixed with "6. Vendor Expenses".  Every chunk therefore has one clear section.
3. Blocks are packed greedily up to ``chunk_size`` estimated tokens.
4. Tables are atomic when they fit.  An oversized table is split by rows and the
   header row is repeated in every piece, so each piece is still interpretable.
5. Oversized prose is split on sentence boundaries with ``chunk_overlap`` overlap
   (LlamaIndex ``SentenceSplitter``).  Between packed blocks the last paragraph is
   carried over as overlap when it is small enough.
6. Fragments smaller than ``min_chunk_size`` are merged into the following chunk.

Sizes are *estimated tokens* = characters / 4 (a good average for English/₹ text and
independent of any tokenizer download).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

from backend.ingestion.markdown_utils import PAGE_MARKER_RE, SHEET_HEADING_PREFIX

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+•●▪]|\d+[.)])\s+")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")

# Keys copied from document metadata to every node.
NODE_DOCUMENT_KEYS = (
    "document_id", "doc_code", "title", "department", "department_slug", "declared_department", "file_type",
    "source_filename", "source_path", "document_type", "version", "status", "effective_date",
    "classification", "related_source_code",
    # Kalakriti product/region/craft documents (see scripts/generate_documents.py)
    "product_id", "city", "craft_category", "product_url", "price_inr", "rating", "availability",
)
# Only these are included in the text that gets embedded (short, high-signal context).
EMBED_METADATA_KEYS = ("title", "department", "doc_code", "document_type", "section_path", "city", "craft_category")


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


@dataclass
class Block:
    kind: str                       # heading | prose | list | table
    text: str
    page: int | None
    path: tuple[str, ...]


@dataclass
class _Chunk:
    blocks: list[Block] = field(default_factory=list)
    path: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

    @property
    def body_tokens(self) -> int:
        return sum(estimate_tokens(b.text) for b in self.blocks if b.kind != "heading")


# ---------------------------------------------------------------------------- block parsing
def parse_blocks(markdown: str) -> list[Block]:
    blocks: list[Block] = []
    stack: list[tuple[int, str]] = []
    page: int | None = None
    buffer: list[str] = []
    buffer_kind = "prose"

    def path() -> tuple[str, ...]:
        return tuple(title for _, title in stack)

    def flush() -> None:
        nonlocal buffer, buffer_kind
        if buffer:
            blocks.append(Block(buffer_kind, "\n".join(buffer).strip(), page, path()))
        buffer, buffer_kind = [], "prose"

    for raw in markdown.split("\n"):
        line = raw.rstrip()
        marker = PAGE_MARKER_RE.match(line)
        if marker:
            flush()
            page = int(marker.group(1))
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            level, title = len(heading.group(1)), heading.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            blocks.append(Block("heading", line.strip(), page, path()))
            continue
        if not line.strip():
            flush()
            continue
        is_table_line = line.lstrip().startswith("|")
        if buffer and (buffer_kind == "table") != is_table_line:
            flush()
        if not buffer:
            buffer_kind = "table" if is_table_line else ("list" if _LIST_RE.match(line) else "prose")
        buffer.append(line)
    flush()
    return blocks


# ---------------------------------------------------------------------------- splitting oversized blocks
def _split_table(text: str, limit: int) -> list[str]:
    lines = text.split("\n")
    header = lines[:2] if len(lines) > 1 and _TABLE_SEP_RE.match(lines[1]) else lines[:1]
    rows = lines[len(header):]
    header_text = "\n".join(header)
    pieces, current = [], []
    for row in rows:
        candidate = "\n".join([header_text, *current, row])
        if current and estimate_tokens(candidate) > limit:
            pieces.append("\n".join([header_text, *current]))
            current = []
        current.append(row)
    if current:
        pieces.append("\n".join([header_text, *current]))
    return pieces or [text]


def _split_lines(text: str, limit: int) -> list[str]:
    pieces, current = [], []
    for line in text.split("\n"):
        if current and estimate_tokens("\n".join([*current, line])) > limit:
            pieces.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        pieces.append("\n".join(current))
    return pieces


def _sheet_of(chunk: "_Chunk") -> str | None:
    return chunk.path[0] if chunk.path and chunk.path[0].startswith(SHEET_HEADING_PREFIX) else None


def _same_sheet(a: "_Chunk", b: "_Chunk") -> bool:
    """Never merge across worksheets: the sheet name is part of a chunk's meaning."""
    return _sheet_of(a) == _sheet_of(b)


class MarkdownChunker:
    def __init__(self, chunk_size: int = 400, chunk_overlap: int = 60, min_chunk_size: int = 40):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        # SentenceSplitter with a custom tokenizer: no tiktoken download needed.
        self._sentence_splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            tokenizer=lambda text: range(estimate_tokens(text)),
        )

    def _explode(self, block: Block) -> list[Block]:
        if estimate_tokens(block.text) <= self.chunk_size:
            return [block]
        if block.kind == "table":
            texts = _split_table(block.text, self.chunk_size)
        elif block.kind == "list":
            texts = _split_lines(block.text, self.chunk_size)
        else:
            texts = self._sentence_splitter.split_text(block.text)
        return [Block(block.kind, t, block.page, block.path) for t in texts if t.strip()]

    # ------------------------------------------------------------------ packing
    def _sections(self, blocks: list[Block]) -> Iterable[list[Block]]:
        current: list[Block] = []
        for block in blocks:
            if current and block.path != current[0].path:
                yield current
                current = []
            current.append(block)
        if current:
            yield current

    def _pack(self, section: list[Block]) -> list[_Chunk]:
        chunks: list[_Chunk] = []
        current = _Chunk(path=section[0].path)
        for original in section:
            for block in self._explode(original):
                size = estimate_tokens(block.text)
                if current.blocks and current.tokens + size > self.chunk_size:
                    chunks.append(current)
                    nxt = _Chunk(path=section[0].path)
                    last = current.blocks[-1]
                    if last.kind in {"prose", "list"} and estimate_tokens(last.text) <= self.chunk_overlap:
                        nxt.blocks.append(last)  # carry the final paragraph over as overlap
                    current = nxt
                current.blocks.append(block)
        if current.blocks:
            chunks.append(current)
        return [c for c in chunks if c.body_tokens > 0]  # drop heading-only chunks

    def _merge_small(self, chunks: list[_Chunk]) -> list[_Chunk]:
        merged: list[_Chunk] = []
        carry: _Chunk | None = None
        for chunk in chunks:
            if carry is not None:
                if carry.tokens + chunk.tokens <= self.chunk_size and _same_sheet(carry, chunk):
                    dominant = chunk.path if chunk.body_tokens >= carry.body_tokens else carry.path
                    chunk = _Chunk(blocks=[*carry.blocks, *chunk.blocks], path=dominant)
                else:
                    merged.append(carry)
                carry = None
            if chunk.body_tokens < self.min_chunk_size:
                carry = chunk
            else:
                merged.append(chunk)
        if carry is not None:
            merged.append(carry)
        return merged

    # ------------------------------------------------------------------ public
    def chunk(self, markdown: str, document_metadata: dict[str, Any]) -> list[TextNode]:
        blocks = parse_blocks(markdown)
        chunks: list[_Chunk] = []
        for section in self._sections(blocks):
            chunks.extend(self._pack(section))
        chunks = self._merge_small(chunks)

        document_id = document_metadata["document_id"]
        base = {k: document_metadata[k] for k in NODE_DOCUMENT_KEYS if document_metadata.get(k) not in (None, "")}
        nodes: list[TextNode] = []
        total = len(chunks)
        for index, chunk in enumerate(chunks):
            pages = [b.page for b in chunk.blocks if b.page is not None]
            kinds = {b.kind for b in chunk.blocks if b.kind != "heading"}
            path = chunk.path
            metadata: dict[str, Any] = dict(base)
            metadata["chunk_index"] = index
            metadata["chunk_count"] = total
            metadata["chunk_kind"] = kinds.pop() if len(kinds) == 1 else "mixed"
            if path:
                metadata["section_path"] = " > ".join(path)
                metadata["section"] = path[-1]
                if path[0].startswith(SHEET_HEADING_PREFIX):
                    metadata["sheet_name"] = path[0][len(SHEET_HEADING_PREFIX):]
            if pages:
                metadata["page_number"] = min(pages)
                metadata["page_end"] = max(pages)
            node = TextNode(
                id_=f"{document_id}::{index:04d}",
                text=chunk.text,
                metadata=metadata,
                excluded_embed_metadata_keys=[k for k in metadata if k not in EMBED_METADATA_KEYS],
                excluded_llm_metadata_keys=list(metadata),
                relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id=document_id)},
            )
            nodes.append(node)
        return nodes
