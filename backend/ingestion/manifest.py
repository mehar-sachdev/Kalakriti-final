"""The processing manifest: what was parsed, when, with what, and with what result.

It is also the idempotency ledger: a document is re-parsed only when its checksum,
the parser configuration or the output file changed (or ``--force`` is given).
Writes are atomic (temp file + rename) so an interrupted run cannot corrupt it.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
CSV_COLUMNS = [
    "document_id", "department", "source_path", "file_type", "status", "validation_status", "parser",
    "parser_version", "page_count", "char_count", "word_recall", "number_recall", "processing_timestamp",
    "checksum_sha256", "indexed_at", "chunk_count",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Manifest:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.documents: dict[str, dict[str, Any]] = {}
        self.generated_at: str | None = None

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls, path: Path) -> "Manifest":
        manifest = cls(path)
        if Path(path).exists():
            try:
                raw = json.loads(Path(path).read_text(encoding="utf-8"))
                manifest.documents = raw.get("documents", {})
                manifest.generated_at = raw.get("generated_at")
            except (json.JSONDecodeError, OSError):
                # a corrupt manifest just means "re-process everything"
                manifest.documents = {}
        return manifest

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.generated_at = utc_now()
        payload = {"schema_version": SCHEMA_VERSION, "generated_at": self.generated_at, "documents": self.documents}
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".manifest-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        self._write_csv(self.path.with_suffix(".csv"))

    def _write_csv(self, path: Path) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for entry in sorted(self.documents.values(), key=lambda e: (e.get("department", ""), e.get("source_path", ""))):
                validation = entry.get("validation") or {}
                stats = validation.get("stats") or {}
                index = entry.get("index") or {}
                writer.writerow({
                    "document_id": entry.get("document_id"),
                    "department": entry.get("department"),
                    "source_path": entry.get("source_path"),
                    "file_type": entry.get("file_type"),
                    "status": entry.get("status"),
                    "validation_status": validation.get("status"),
                    "parser": entry.get("parser"),
                    "parser_version": entry.get("parser_version"),
                    "page_count": entry.get("page_count"),
                    "char_count": entry.get("char_count"),
                    "word_recall": stats.get("word_recall"),
                    "number_recall": stats.get("number_recall"),
                    "processing_timestamp": entry.get("processing_timestamp"),
                    "checksum_sha256": entry.get("checksum_sha256"),
                    "indexed_at": index.get("indexed_at"),
                    "chunk_count": index.get("chunk_count"),
                })

    # ------------------------------------------------------------------ access
    def get(self, document_id: str) -> dict[str, Any] | None:
        return self.documents.get(document_id)

    def set(self, document_id: str, entry: dict[str, Any]) -> None:
        self.documents[document_id] = entry

    def remove(self, document_id: str) -> None:
        self.documents.pop(document_id, None)

    def successful(self) -> list[dict[str, Any]]:
        return [e for e in self.documents.values() if e.get("status") == "success"]


def needs_processing(
    entry: dict[str, Any] | None,
    checksum: str,
    config_hash: str,
    processed_file: Path,
    force: bool = False,
) -> str | None:
    """Return the reason a document must be (re)processed, or None if it is up to date."""
    if force:
        return "forced"
    if entry is None:
        return "new document"
    if entry.get("status") != "success":
        return "previous attempt failed"
    if entry.get("checksum_sha256") != checksum:
        return "source changed"
    if entry.get("parse_config_hash") != config_hash:
        return "parser configuration changed"
    if not processed_file.exists():
        return "processed file missing"
    return None
