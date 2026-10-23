"""Document registry: which documents are indexed, with which model and chunking."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.config import Settings
from backend.database.connection import explain_db_error, safe_identifier
from backend.database.schema import chunk_table_name

logger = logging.getLogger(__name__)


class DocumentRegistry:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        schema = safe_identifier(settings.db_schema)
        self.docs = f"{schema}.{safe_identifier(settings.documents_table)}"
        self.chunks = f"{schema}.{chunk_table_name(settings)}"

    def _run(self, sql: str, params: dict[str, Any] | None = None, *, fetch: bool = False):
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text(sql), params or {})
                return [dict(r._mapping) for r in result] if fetch else None
        except SQLAlchemyError as exc:
            raise explain_db_error(exc) from exc

    # ---------------------------------------------------------------- writes
    def upsert(self, record: dict[str, Any]) -> None:
        params = {**record, "metadata": json.dumps(record.get("metadata", {}), ensure_ascii=False)}
        self._run(
            f"""
            insert into {self.docs} (document_id, title, doc_code, department, department_slug, source_filename,
                source_path, file_type, document_type, version, status, classification, page_count, chunk_count,
                checksum_sha256, parser, embedding_signature, chunk_config, indexed_at, metadata)
            values (:document_id, :title, :doc_code, :department, :department_slug, :source_filename,
                :source_path, :file_type, :document_type, :version, :status, :classification, :page_count, :chunk_count,
                :checksum_sha256, :parser, :embedding_signature, :chunk_config, now(), cast(:metadata as jsonb))
            on conflict (document_id) do update set
                title=excluded.title, doc_code=excluded.doc_code, department=excluded.department,
                department_slug=excluded.department_slug, source_filename=excluded.source_filename,
                source_path=excluded.source_path, file_type=excluded.file_type, document_type=excluded.document_type,
                version=excluded.version, status=excluded.status, classification=excluded.classification,
                page_count=excluded.page_count, chunk_count=excluded.chunk_count, checksum_sha256=excluded.checksum_sha256,
                parser=excluded.parser, embedding_signature=excluded.embedding_signature,
                chunk_config=excluded.chunk_config, indexed_at=now(), metadata=excluded.metadata
            """,
            params,
        )

    def delete(self, document_id: str) -> None:
        self._run(f"delete from {self.docs} where document_id = :id", {"id": document_id})

    def delete_chunks(self, document_id: str) -> int:
        """Remove all chunk rows of one document (also used for pruning)."""
        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    text(f"delete from {self.chunks} where metadata_ ->> 'document_id' = :id"), {"id": document_id}
                )
                return result.rowcount or 0
        except SQLAlchemyError as exc:
            raise explain_db_error(exc) from exc

    def reset(self) -> None:
        """Drop all indexed data (used when the embedding model changes)."""
        self._run(f"truncate table {self.chunks} restart identity")
        self._run(f"truncate table {self.docs}")

    # ---------------------------------------------------------------- reads
    def get(self, document_id: str) -> dict[str, Any] | None:
        rows = self._run(f"select * from {self.docs} where document_id = :id", {"id": document_id}, fetch=True)
        return rows[0] if rows else None

    def list_documents(self, department_slug: str | None = None) -> list[dict[str, Any]]:
        if department_slug:
            return self._run(
                f"select * from {self.docs} where department_slug = :d order by source_path", {"d": department_slug}, fetch=True
            )
        return self._run(f"select * from {self.docs} order by department, source_path", fetch=True)

    def all_ids(self) -> set[str]:
        return {r["document_id"] for r in self._run(f"select document_id from {self.docs}", fetch=True)}

    def signatures(self) -> set[str]:
        return {r["embedding_signature"] for r in self._run(f"select distinct embedding_signature from {self.docs}", fetch=True)}

    def department_stats(self) -> list[dict[str, Any]]:
        return self._run(
            f"""select department_slug as slug, min(department) as name, count(*) as document_count,
                       coalesce(sum(chunk_count),0) as chunk_count
                from {self.docs} group by department_slug order by min(department)""",
            fetch=True,
        )

    def chunk_total(self) -> int:
        rows = self._run(f"select coalesce(sum(chunk_count),0) as n from {self.docs}", fetch=True)
        return int(rows[0]["n"])

    def chunks_for(self, document_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return self._run(
            f"""select node_id, text, metadata_ ->> 'page_number' as page, metadata_ ->> 'section_path' as section
                from {self.chunks} where metadata_ ->> 'document_id' = :id
                order by (metadata_ ->> 'chunk_index')::int limit :n""",
            {"id": document_id, "n": limit}, fetch=True,
        )

    def rls_enabled(self) -> bool:
        schema, _, table = self.chunks.partition(".")
        rows = self._run(
            """select c.relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace
               where n.nspname=:s and c.relname=:t""", {"s": schema, "t": table}, fetch=True,
        )
        return bool(rows and rows[0]["relrowsecurity"])
