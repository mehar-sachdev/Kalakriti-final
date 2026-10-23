"""Stage 01 + 02: parse every document to Markdown, validate it, record it.

Robustness rules (assignment: "one corrupted document must not terminate the batch"):
each document is processed inside its own try/except; failures are recorded in the
manifest with a redacted error message and the loop continues.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.config import Settings
from backend.exceptions import ParsingError
from backend.ingestion.discovery import UNASSIGNED_DEPARTMENT, discover_documents
from backend.ingestion.manifest import Manifest, needs_processing, utc_now
from backend.ingestion.markdown_utils import clean_markdown, write_processed_markdown
from backend.ingestion.metadata import build_document_metadata, cross_references
from backend.ingestion.parser import ParserRegistry
from backend.ingestion.validator import validate_markdown
from backend.logging_config import redact
from backend.models.documents import ParsedDocument, SourceDocument

logger = logging.getLogger(__name__)
PARSE_SCHEMA_VERSION = 2  # bump when the Markdown output format changes


@dataclass
class DocResult:
    document_id: str
    source_path: str
    department: str
    file_type: str
    status: str                       # success | failed | skipped
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    validation_status: str | None = None
    duration_s: float = 0.0
    char_count: int = 0
    page_count: int | None = None
    word_recall: float | None = None
    number_recall: float | None = None


@dataclass
class ParseRunSummary:
    input_dir: str
    output_dir: str
    started_at: str
    finished_at: str = ""
    duration_s: float = 0.0
    parser_version: str = ""
    results: list[DocResult] = field(default_factory=list)
    unsupported: list[dict[str, str]] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for r in self.results if r.status == status)

    @property
    def total(self) -> int:
        return len(self.results)


def parse_config_hash(settings: Settings, parser_version: str) -> str:
    payload = {
        "schema": PARSE_SCHEMA_VERSION, "docling": parser_version, "ocr": settings.docling_do_ocr,
        "tables": settings.docling_table_structure, "promote": settings.promote_numbered_headings,
        "fallback": settings.enable_parser_fallback,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def processed_relpath(source: SourceDocument) -> str:
    parts = source.relative_path.split("/")
    within = parts if source.department_name == UNASSIGNED_DEPARTMENT and len(parts) == 1 else parts[1:]
    return f"{source.department_slug}/{'/'.join(within)}.md"


def parse_documents(
    settings: Settings,
    input_dir: Path | None = None,
    output_dir: Path | None = None,
    *,
    department: str | None = None,
    force: bool = False,
    registry: ParserRegistry | None = None,
) -> ParseRunSummary:
    input_dir = Path(input_dir or settings.raw_dir)
    output_dir = Path(output_dir or settings.processed_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    summary = ParseRunSummary(str(input_dir), str(output_dir), started_at=utc_now())

    discovery = discover_documents(input_dir, department=department)
    summary.unsupported = discovery.skipped
    registry = registry or ParserRegistry(settings)
    manifest = Manifest.load(output_dir / "manifest.json")
    version = registry.docling_version
    summary.parser_version = f"docling {version}"
    config_hash = parse_config_hash(settings, version)

    if department is None:
        found = {d.document_id for d in discovery.documents}
        summary.missing_sources = sorted(i for i in manifest.documents if i not in found)
        for missing in summary.missing_sources:
            logger.warning("Source file for %s no longer exists (run index --prune to drop it).", missing)
            manifest.documents[missing]["source_missing"] = True

    try:
        for position, source in enumerate(discovery.documents, start=1):
            entry = manifest.get(source.document_id)
            relpath = processed_relpath(source)
            out_path = output_dir / relpath
            reason = needs_processing(entry, source.checksum, config_hash, out_path, force)
            if reason is None:
                logger.info("[%d/%d] Unchanged, skipping %s", position, len(discovery.documents), source.relative_path)
                if entry:
                    entry.pop("source_missing", None)
                summary.results.append(DocResult(
                    source.document_id, source.relative_path, source.department_name, source.file_type,
                    "skipped", "unchanged since last successful run", page_count=entry.get("page_count") if entry else None,
                    char_count=(entry or {}).get("char_count", 0),
                ))
                continue

            logger.info("[%d/%d] Processing %s (%s)", position, len(discovery.documents), source.relative_path, reason)
            result = _process_one(settings, registry, manifest, source, out_path, relpath, config_hash)
            summary.results.append(result)
            if result.status == "success":
                logger.info("Successfully converted %s (%d chars, validation=%s)", source.relative_path, result.char_count, result.validation_status)
            else:
                logger.error("Unable to process %s: %s", source.relative_path, result.reason)
    finally:
        manifest.save()

    summary.duration_s = round(time.perf_counter() - started, 2)
    summary.finished_at = utc_now()
    logger.info(
        "Parsing finished: %d ok, %d failed, %d skipped in %.1fs",
        summary.count("success"), summary.count("failed"), summary.count("skipped"), summary.duration_s,
    )
    return summary


def _process_one(settings, registry, manifest, source, out_path, relpath, config_hash) -> DocResult:
    t0 = time.perf_counter()
    base = DocResult(source.document_id, source.relative_path, source.department_name, source.file_type, "failed")
    previous = manifest.get(source.document_id) or {}
    try:
        if source.size_bytes == 0:
            raise ParsingError("File is empty (0 bytes).")
        parsed: ParsedDocument = registry.parse(source)
        markdown, clean_stats = clean_markdown(parsed.markdown, promote_headings=settings.promote_numbered_headings)
        if clean_stats["headings_promoted"]:
            parsed.warnings.append(f"Recovered {clean_stats['headings_promoted']} numbered section heading(s) from plain paragraphs.")
        validation = validate_markdown(markdown, source, parsed)
        if validation.status == "error":
            messages = "; ".join(i.message for i in validation.issues if i.level == "error")
            raise ParsingError(f"Validation failed: {messages}")

        metadata = build_document_metadata(source, markdown)
        processed_at = utc_now()
        write_processed_markdown(out_path, markdown, {
            "document_id": source.document_id, "source_path": source.relative_path,
            "department": source.department_name, "department_slug": source.department_slug,
            "file_type": source.file_type, "checksum_sha256": source.checksum,
            "parser": f"{parsed.parser} {parsed.parser_version}", "page_count": parsed.page_count,
            "processed_at": processed_at, "title": metadata.get("title"), "doc_code": metadata.get("doc_code"),
        })
        manifest.set(source.document_id, {
            "document_id": source.document_id,
            "source_filename": source.filename,
            "source_path": source.relative_path,
            "department": source.department_name,
            "department_slug": source.department_slug,
            "file_type": source.file_type,
            "size_bytes": source.size_bytes,
            "checksum_sha256": source.checksum,
            "processed_path": relpath,
            "processing_timestamp": processed_at,
            "parser": parsed.parser,
            "parser_version": parsed.parser_version,
            "parse_config_hash": config_hash,
            "page_count": parsed.page_count,
            "char_count": len(markdown),
            "status": "success",
            "error": None,
            "warnings": parsed.warnings,
            "validation": validation.to_dict(),
            "metadata": metadata,
            "cross_references": cross_references(markdown, metadata.get("doc_code")),
            "index": None,  # content changed -> must be (re)indexed
        })
        stats = validation.stats
        base.status = "success"
        base.warnings = parsed.warnings + [i.message for i in validation.issues if i.level == "warning"]
        base.validation_status = validation.status
        base.char_count = len(markdown)
        base.page_count = parsed.page_count
        base.word_recall = stats.get("word_recall")
        base.number_recall = stats.get("number_recall")
    except Exception as exc:  # noqa: BLE001 - one bad file must never stop the batch
        message = redact(getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}")
        base.reason = message
        manifest.set(source.document_id, {
            "document_id": source.document_id, "source_filename": source.filename, "source_path": source.relative_path,
            "department": source.department_name, "department_slug": source.department_slug, "file_type": source.file_type,
            "size_bytes": source.size_bytes, "checksum_sha256": source.checksum, "processing_timestamp": utc_now(),
            "parse_config_hash": config_hash, "status": "failed", "error": message, "warnings": [],
            "index": previous.get("index"), "metadata": previous.get("metadata", {}),
        })
        if not isinstance(exc, ParsingError):
            logger.debug("Unexpected error while parsing %s", source.relative_path, exc_info=True)
    base.duration_s = round(time.perf_counter() - t0, 2)
    return base
