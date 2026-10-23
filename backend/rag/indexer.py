"""Stage 03: chunk -> embed -> store in Supabase pgvector -> register.

Properties
* Incremental / idempotent: a document is re-indexed only if its checksum, the chunking
  configuration or the embedding model changed (or ``force``).
* Per-document safety: embeddings are computed *before* old rows are touched; a failure
  leaves the previous version intact (or, if the write itself fails, unregistered so the next
  run retries it).  One failing document never stops the batch.
* Embedding-space guard: vectors from different models are never mixed in one table.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llama_index.core.schema import MetadataMode

from backend.config import Settings
from backend.database.connection import get_engine
from backend.database.registry import DocumentRegistry
from backend.database.vector_store import build_vector_store
from backend.exceptions import EmbeddingError, IndexingError, RAGError
from backend.ingestion.manifest import Manifest, utc_now
from backend.ingestion.markdown_utils import read_processed_markdown
from backend.logging_config import redact
from backend.rag.chunking import MarkdownChunker
from backend.rag.embeddings import get_embed_model

logger = logging.getLogger(__name__)


@dataclass
class IndexSummary:
    indexed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    pruned: list[str] = field(default_factory=list)
    chunks_written: int = 0
    duration_s: float = 0.0
    reset: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "indexed": len(self.indexed), "skipped": len(self.skipped), "failed": len(self.failed),
            "pruned": len(self.pruned), "chunks_written": self.chunks_written,
            "duration_seconds": self.duration_s, "errors": self.failed,
        }


def chunk_config(settings: Settings) -> str:
    return f"{settings.chunk_size}/{settings.chunk_overlap}/{settings.min_chunk_size}"


class Indexer:
    def __init__(self, settings: Settings, *, embed_model=None, vector_store=None, registry: DocumentRegistry | None = None):
        settings.require("index")
        self.settings = settings
        self.embed_model = embed_model or get_embed_model(settings)
        self.vector_store = vector_store or build_vector_store(settings)
        self.registry = registry or DocumentRegistry(get_engine(settings), settings)
        self.chunker = MarkdownChunker(settings.chunk_size, settings.chunk_overlap, settings.min_chunk_size)

    # ------------------------------------------------------------------ helpers
    def _needs_index(self, entry: dict[str, Any], record: dict[str, Any] | None, force: bool) -> str | None:
        if force:
            return "forced"
        if record is None:
            return "not indexed yet"
        if record["checksum_sha256"] != entry["checksum_sha256"]:
            return "source changed"
        if record["embedding_signature"] != self.settings.embedding_signature:
            return "embedding model changed"
        if record["chunk_config"] != chunk_config(self.settings):
            return "chunking configuration changed"
        return None

    def _embed(self, nodes) -> None:
        texts = [n.get_content(metadata_mode=MetadataMode.EMBED) for n in nodes]
        try:
            vectors = self.embed_model.get_text_embedding_batch(texts, show_progress=False)
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(
                redact(f"Embedding failed: {type(exc).__name__}: {exc}")[:300],
                hint="For huggingface: check internet access for the first model download. For ollama: run `ollama serve` and `ollama pull <model>`.",
            ) from exc
        expected = self.settings.resolved_embedding_dim
        for node, vector in zip(nodes, vectors):
            if len(vector) != expected:
                raise EmbeddingError(
                    f"Model returned {len(vector)}-dimensional vectors but EMBEDDING_DIM/the schema expects {expected}.",
                    hint="Fix EMBEDDING_DIM, or re-create the table with --reset after changing the model.",
                )
            node.embedding = vector

    # ------------------------------------------------------------------ one document
    def index_entry(self, entry: dict[str, Any], processed_dir: Path) -> int:
        markdown_path = processed_dir / entry["processed_path"]
        if not markdown_path.exists():
            raise IndexingError(f"Processed Markdown missing: {entry['processed_path']}", hint="Run the parse stage first.")
        _, body = read_processed_markdown(markdown_path)
        nodes = self.chunker.chunk(body, entry["metadata"])
        if not nodes:
            raise IndexingError("Chunking produced no chunks (document has no text).")
        self._embed(nodes)

        document_id = entry["document_id"]
        self.registry.delete(document_id)           # forget first: a crash below => retried next run
        self.vector_store.delete(ref_doc_id=document_id)
        self.vector_store.add(nodes)
        meta = entry["metadata"]
        self.registry.upsert({
            "document_id": document_id, "title": meta.get("title"), "doc_code": meta.get("doc_code"),
            "department": entry["department"], "department_slug": entry["department_slug"],
            "source_filename": entry["source_filename"], "source_path": entry["source_path"],
            "file_type": entry["file_type"], "document_type": meta.get("document_type"),
            "version": meta.get("version"), "status": meta.get("status"), "classification": meta.get("classification"),
            "page_count": entry.get("page_count"), "chunk_count": len(nodes), "checksum_sha256": entry["checksum_sha256"],
            "parser": f"{entry.get('parser')} {entry.get('parser_version')}", "embedding_signature": self.settings.embedding_signature,
            "chunk_config": chunk_config(self.settings),
            "metadata": {k: v for k, v in meta.items() if k not in {"document_id"}},
        })
        return len(nodes)

    # ------------------------------------------------------------------ batch
    def index_documents(
        self, manifest: Manifest, processed_dir: Path, *, department: str | None = None,
        force: bool = False, prune: bool = False, reset: bool = False,
    ) -> IndexSummary:
        started = time.perf_counter()
        summary = IndexSummary(reset=reset)

        existing_signatures = self.registry.signatures()
        if reset:
            logger.warning("Resetting the vector store: all indexed documents will be removed and rebuilt.")
            self.registry.reset()
            force = True
        elif existing_signatures and existing_signatures != {self.settings.embedding_signature}:
            raise IndexingError(
                f"The index was built with {sorted(existing_signatures)} but the configuration now says "
                f"'{self.settings.embedding_signature}'.",
                hint="Vectors from different models cannot be mixed. Re-run with --reset to rebuild the whole index.",
            )

        wanted = department.strip().lower() if department else None
        candidates = [
            e for e in manifest.documents.values()
            if e.get("status") == "success" and not e.get("source_missing")
            and (not wanted or wanted in {e["department"].lower(), e["department_slug"]})
        ]
        logger.info("Indexing %d parsed documents", len(candidates))
        registered = {r["document_id"]: r for r in self.registry.list_documents()}

        for position, entry in enumerate(sorted(candidates, key=lambda e: e["source_path"]), start=1):
            document_id = entry["document_id"]
            reason = self._needs_index(entry, registered.get(document_id), force)
            if reason is None:
                logger.info("[%d/%d] Index up to date: %s", position, len(candidates), entry["source_path"])
                summary.skipped.append(document_id)
                continue
            logger.info("[%d/%d] Indexing %s (%s)", position, len(candidates), entry["source_path"], reason)
            try:
                count = self.index_entry(entry, processed_dir)
            except RAGError as exc:
                summary.failed[document_id] = exc.message
                logger.error("Unable to index %s: %s", entry["source_path"], exc.message)
                continue
            except Exception as exc:  # noqa: BLE001 - keep the batch going
                summary.failed[document_id] = redact(f"{type(exc).__name__}: {exc}")[:300]
                logger.error("Unable to index %s: %s", entry["source_path"], summary.failed[document_id])
                continue
            entry["index"] = {
                "indexed_at": utc_now(), "chunk_count": count, "embedding_signature": self.settings.embedding_signature,
                "chunk_config": chunk_config(self.settings), "checksum_sha256": entry["checksum_sha256"],
            }
            summary.indexed.append(document_id)
            summary.chunks_written += count
            logger.info("Indexed %d nodes for %s", count, entry["source_path"])

        if prune and not wanted:
            keep = {e["document_id"] for e in candidates}
            for stale in sorted(self.registry.all_ids() - keep):
                self.vector_store.delete(ref_doc_id=stale)
                self.registry.delete(stale)
                manifest.documents.pop(stale, None)
                summary.pruned.append(stale)
                logger.info("Pruned %s (no longer in the source set)", stale)
            for missing in [k for k, e in manifest.documents.items() if e.get("source_missing")]:
                manifest.documents.pop(missing, None)

        manifest.save()
        summary.duration_s = round(time.perf_counter() - started, 2)
        logger.info(
            "Indexing finished: %d indexed, %d up to date, %d failed, %d chunks in %.1fs",
            len(summary.indexed), len(summary.skipped), len(summary.failed), summary.chunks_written, summary.duration_s,
        )
        return summary
