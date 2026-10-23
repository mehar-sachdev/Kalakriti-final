"""Command-line ingestion.

    python -m backend.ingest list                       # what would be processed
    python -m backend.ingest parse   [--force]          # PDF/DOCX/XLSX -> Markdown + manifest + report
    python -m backend.ingest validate [--sample 3]      # re-check Markdown vs sources, write review samples
    python -m backend.ingest index   [--force|--reset]  # chunk -> embed -> Supabase pgvector
    python -m backend.ingest all                        # parse + index

Every command is idempotent: unchanged documents are skipped.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from backend.config import Settings, get_settings
from backend.exceptions import RAGError
from backend.ingestion.discovery import discover_documents
from backend.ingestion.manifest import Manifest
from backend.ingestion.markdown_utils import read_processed_markdown
from backend.ingestion.pipeline import ParseRunSummary, parse_documents
from backend.ingestion.report import write_report
from backend.ingestion.validator import extract_reference, validate_markdown
from backend.logging_config import redact, setup_logging
from backend.models.documents import SourceDocument

logger = logging.getLogger("backend.ingest")


# ---------------------------------------------------------------------------- programmatic API
def run_parse(settings: Settings, *, input_dir=None, output_dir=None, department=None, force=False) -> ParseRunSummary:
    summary = parse_documents(settings, input_dir, output_dir, department=department, force=force)
    out = Path(output_dir or settings.processed_dir)
    paths = write_report(summary, Manifest.load(out / "manifest.json"), settings.reports_dir)
    logger.info("Parsing report written to %s", paths["markdown"])
    return summary


def run_index(settings: Settings, *, output_dir=None, department=None, force=False, prune=False, reset=False):
    from backend.rag.indexer import Indexer  # imported lazily: needs DB + embedding libraries

    processed = Path(output_dir or settings.processed_dir)
    manifest = Manifest.load(processed / "manifest.json")
    if not manifest.documents:
        raise RAGError("No processed documents found.", hint="Run `python -m backend.ingest parse` first.")
    return Indexer(settings).index_documents(manifest, processed, department=department, force=force, prune=prune, reset=reset)


# ---------------------------------------------------------------------------- printing
def _print_parse_summary(summary: ParseRunSummary) -> None:
    print("\n=== Parsing summary ===")
    print(f"Documents discovered : {summary.total}")
    print(f"  converted          : {summary.count('success')}")
    print(f"  unchanged (skipped): {summary.count('skipped')}")
    print(f"  failed             : {summary.count('failed')}")
    print(f"Unsupported files    : {len(summary.unsupported)}")
    print(f"Duration             : {summary.duration_s}s   ({summary.parser_version})")
    for r in summary.results:
        if r.status == "failed":
            print(f"  FAILED  {r.source_path}: {r.reason}")
        elif r.warnings:
            print(f"  warning {r.source_path}: {r.warnings[0][:110]}")


def _print_index_summary(summary) -> None:
    print("\n=== Indexing summary ===")
    print(f"Indexed documents : {len(summary.indexed)}  ({summary.chunks_written} chunks)")
    print(f"Up to date        : {len(summary.skipped)}")
    print(f"Failed            : {len(summary.failed)}")
    print(f"Pruned            : {len(summary.pruned)}")
    for doc_id, message in summary.failed.items():
        print(f"  FAILED  {doc_id}: {message}")


# ---------------------------------------------------------------------------- validate
def cmd_validate(settings: Settings, input_dir: Path, sample: int, department: str | None) -> int:
    """Re-run every check against the *current* sources and write a human-review file."""
    manifest = Manifest.load(settings.manifest_path)
    discovery = discover_documents(input_dir, department=department)
    by_id = {d.document_id: d for d in discovery.documents}
    lines = ["# Validation report", ""]
    problems = 0
    per_type_shown: dict[str, int] = {}
    samples: list[str] = []
    for entry in sorted(manifest.successful(), key=lambda e: e["source_path"]):
        source: SourceDocument | None = by_id.get(entry["document_id"])
        if source is None:
            continue
        meta, body = read_processed_markdown(settings.processed_dir / entry["processed_path"])
        result = validate_markdown(body, source)
        if result.status != "ok":
            problems += 1
        lines.append(f"- **{entry['source_path']}** - {result.status}; recall words={result.stats.get('word_recall')} numbers={result.stats.get('number_recall')}")
        for issue in result.issues:
            lines.append(f"    - {issue.level}: [{issue.code}] {issue.message}")
        shown = per_type_shown.get(source.file_type, 0)
        if shown < sample:
            per_type_shown[source.file_type] = shown + 1
            reference = extract_reference(source)
            samples += [
                f"\n### {entry['source_path']}\n",
                "**Independent source text (first 700 chars)**\n", "```text", (reference.text[:700] if reference else "n/a"), "```",
                "**Docling Markdown (first 1200 chars)**\n", "```markdown", body[:1200], "```",
            ]
    lines += ["", "## Side-by-side samples for manual review", "", "Compare each pair by eye: tables, numbers (₹), headings and order.", *samples]
    out = settings.reports_dir / "validation_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Validated {len(manifest.successful())} documents; {problems} with warnings/errors. Report: {out}")
    return 0


# ---------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m backend.ingest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, index=False, parse=False):
        p.add_argument("--input", type=Path, help="Source folder (default RAW_DIR, i.e. data/raw)")
        p.add_argument("--output", type=Path, help="Processed folder (default PROCESSED_DIR, i.e. data/processed)")
        p.add_argument("--department", help="Only this department (folder name or slug)")
        p.add_argument("--force", action="store_true", help="Ignore checksums and redo everything")
        p.add_argument("--strict", action="store_true", help="Exit with status 1 if any document failed")
        if index:
            p.add_argument("--prune", action="store_true", help="Delete index entries whose source file disappeared")
            p.add_argument("--reset", action="store_true", help="Wipe the index and rebuild (needed after changing the embedding model)")

    common(sub.add_parser("list", help="Show what would be processed"))
    common(sub.add_parser("parse", help="Convert documents to Markdown"), parse=True)
    v = sub.add_parser("validate", help="Re-validate Markdown against the sources and write review samples")
    common(v)
    v.add_argument("--sample", type=int, default=2, help="Samples per file type in the review file (default 2)")
    common(sub.add_parser("index", help="Chunk, embed and store in pgvector"), index=True)
    common(sub.add_parser("all", help="parse + index"), index=True, parse=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format, settings.log_dir)
    input_dir = Path(args.input) if args.input else settings.raw_dir
    exit_code = 0
    try:
        if args.command == "list":
            result = discover_documents(input_dir, department=args.department)
            print(f"{len(result.documents)} supported documents in {len(result.departments)} departments under {input_dir}")
            for name, count in sorted(result.departments.items()):
                print(f"  {name:<28} {count}")
            for item in result.skipped:
                print(f"  skipped {item['path']}: {item['reason']}")
        elif args.command == "validate":
            return cmd_validate(settings, input_dir, args.sample, args.department)
        else:
            if args.command in {"parse", "all"}:
                summary = run_parse(settings, input_dir=input_dir, output_dir=args.output, department=args.department, force=args.force)
                _print_parse_summary(summary)
                if summary.count("failed") and args.strict:
                    exit_code = 1
            if args.command in {"index", "all"}:
                settings.require("index")
                index_summary = run_index(
                    settings, output_dir=args.output, department=args.department, force=args.force, prune=args.prune, reset=args.reset
                )
                _print_index_summary(index_summary)
                if index_summary.failed and args.strict:
                    exit_code = 1
    except RAGError as exc:
        print(f"\nERROR [{exc.code}]: {redact(exc.message)}", file=sys.stderr)
        if exc.hint:
            print(f"HINT: {exc.hint}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted. Progress made so far is saved; re-run to continue.", file=sys.stderr)
        return 130
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
