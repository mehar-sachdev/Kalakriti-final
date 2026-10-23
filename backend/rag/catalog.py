"""Read-only catalog of documents/departments/stats.

Works offline from ``data/processed/manifest.json`` and, when the database is reachable,
overlays the live registry (which documents are actually indexed, chunk counts).
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from backend.config import Settings
from backend.database.connection import get_engine
from backend.database.registry import DocumentRegistry
from backend.exceptions import DatabaseError, NotFoundError, RAGError
from backend.ingestion.manifest import Manifest
from backend.ingestion.markdown_utils import read_processed_markdown
from backend.models.schemas import DepartmentInfo, DocumentInfo, SourceDetail, StatsResponse
from backend.rag.retrieval import Dept, resolve_department

logger = logging.getLogger(__name__)
MAX_MARKDOWN_CHARS = 60_000


class Catalog:
    def __init__(self, settings: Settings, registry: DocumentRegistry | None = None):
        self.settings = settings
        self._registry = registry

    # ---------------------------------------------------------------- sources
    def _registry_rows(self) -> list[dict[str, Any]] | None:
        if self._registry is None:
            if self.settings.supabase_db_url is None:
                return None
            try:
                self._registry = DocumentRegistry(get_engine(self.settings), self.settings)
            except RAGError:
                return None
        try:
            return self._registry.list_documents()
        except (DatabaseError, RAGError) as exc:
            logger.warning("Registry unavailable, using manifest only: %s", exc.message)
            return None

    def _merged(self) -> tuple[dict[str, DocumentInfo], bool]:
        manifest = Manifest.load(self.settings.manifest_path)
        docs: dict[str, DocumentInfo] = {}
        for entry in manifest.documents.values():
            if entry.get("status") != "success" or entry.get("source_missing"):
                continue
            meta = entry.get("metadata", {})
            docs[entry["document_id"]] = DocumentInfo(
                document_id=entry["document_id"], title=meta.get("title"), doc_code=meta.get("doc_code"),
                source_filename=entry["source_filename"], source_path=entry["source_path"], department=entry["department"],
                department_slug=entry["department_slug"], file_type=entry["file_type"], document_type=meta.get("document_type"),
                version=meta.get("version"), status=meta.get("status"), classification=meta.get("classification"),
                page_count=entry.get("page_count"), chunk_count=(entry.get("index") or {}).get("chunk_count"),
                indexed=False, processing_timestamp=entry.get("processing_timestamp"),
                parser=f"{entry.get('parser')} {entry.get('parser_version')}",
            )
        rows = self._registry_rows()
        live = rows is not None
        if rows is not None:
            indexed_ids = set()
            for r in rows:
                indexed_ids.add(r["document_id"])
                base = docs.get(r["document_id"])
                info = DocumentInfo(
                    document_id=r["document_id"], title=r.get("title"), doc_code=r.get("doc_code"),
                    source_filename=r["source_filename"], source_path=r["source_path"], department=r["department"],
                    department_slug=r["department_slug"], file_type=r["file_type"], document_type=r.get("document_type"),
                    version=r.get("version"), status=r.get("status"), classification=r.get("classification"),
                    page_count=r.get("page_count"), chunk_count=r.get("chunk_count"), indexed=True,
                    processing_timestamp=base.processing_timestamp if base else (r["indexed_at"].isoformat() if r.get("indexed_at") else None),
                    parser=r.get("parser"),
                )
                docs[r["document_id"]] = info
            for doc_id, info in docs.items():  # manifest says indexed but the DB disagrees
                if doc_id not in indexed_ids:
                    info.indexed = False
                    info.chunk_count = None
        return docs, live  # type: ignore[return-value]

    # ---------------------------------------------------------------- public API
    def documents(self, department: str | None = None, document_type: str | None = None) -> list[DocumentInfo]:
        docs, _ = self._merged()
        items = list(docs.values())
        if department:
            known = {d.department_slug: Dept(d.department_slug, d.department) for d in items}
            slug = resolve_department(department, list(known.values()))  # same rules as /query; 422 if unknown
            if slug:
                items = [d for d in items if d.department_slug == slug]
        if document_type:
            items = [d for d in items if (d.document_type or "").lower() == document_type.strip().lower()]
        return sorted(items, key=lambda d: (d.department, d.source_path))

    def departments(self) -> list[DepartmentInfo]:
        docs, _ = self._merged()
        grouped: dict[str, list[DocumentInfo]] = {}
        for d in docs.values():
            grouped.setdefault(d.department_slug, []).append(d)
        out = []
        for slug, items in grouped.items():
            chunks = sum(d.chunk_count or 0 for d in items)
            out.append(DepartmentInfo(slug=slug, name=items[0].department, document_count=len(items), chunk_count=chunks or None))
        return sorted(out, key=lambda d: d.name.lower())

    def stats(self) -> StatsResponse:
        docs, live = self._merged()
        manifest = Manifest.load(self.settings.manifest_path)
        parsing = Counter(e.get("status", "unknown") for e in manifest.documents.values())
        chunk_total = sum(d.chunk_count or 0 for d in docs.values()) if live else None
        return StatsResponse(
            documents_total=len(docs),
            documents_indexed=sum(1 for d in docs.values() if d.indexed),
            chunks_total=chunk_total,
            by_department=dict(Counter(d.department for d in docs.values())),
            by_file_type=dict(Counter(d.file_type for d in docs.values())),
            parsing=dict(parsing),
            embedding=self.settings.embedding_signature,
            llm_model=self.settings.ollama_model,
            source="database" if live else "manifest",
        )

    def source_detail(self, document_id: str, include_markdown: bool = False) -> SourceDetail:
        docs, _ = self._merged()
        info = docs.get(document_id)
        if info is None:
            raise NotFoundError(f"Unknown document '{document_id}'.", hint="List valid ids with GET /documents.")
        manifest = Manifest.load(self.settings.manifest_path)
        entry = manifest.get(document_id) or {}
        detail = SourceDetail(
            **info.model_dump(),
            header_metadata=entry.get("metadata", {}),
            validation=entry.get("validation", {}),
            related_documents=entry.get("cross_references", []),
        )
        if include_markdown and entry.get("processed_path"):
            path = self.settings.processed_dir / entry["processed_path"]
            if path.exists():
                _, body = read_processed_markdown(path)
                detail.markdown = body[:MAX_MARKDOWN_CHARS]
                detail.markdown_truncated = len(body) > MAX_MARKDOWN_CHARS
        return detail
