"""Parsing report (reports/parsing_report.json + .md)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from backend.ingestion.manifest import Manifest, utc_now
from backend.ingestion.pipeline import ParseRunSummary


def build_report(summary: ParseRunSummary, manifest: Manifest) -> dict[str, Any]:
    results = summary.results
    by_type = Counter(r.file_type for r in results)
    by_dept = Counter(r.department for r in results)
    per_status_type: dict[str, dict[str, int]] = {}
    for r in results:
        per_status_type.setdefault(r.file_type, Counter())[r.status] += 1  # type: ignore[arg-type]

    validations = Counter(r.validation_status for r in results if r.validation_status)
    recalls = [r.word_recall for r in results if r.word_recall is not None]
    nrecalls = [r.number_recall for r in results if r.number_recall is not None]

    corpus_entries = list(manifest.documents.values())
    corpus = {
        "documents_in_manifest": len(corpus_entries),
        "successful": sum(1 for e in corpus_entries if e.get("status") == "success"),
        "failed": sum(1 for e in corpus_entries if e.get("status") == "failed"),
        "by_department": dict(Counter(e.get("department") for e in corpus_entries)),
        "by_file_type": dict(Counter(e.get("file_type") for e in corpus_entries)),
    }
    return {
        "generated_at": utc_now(),
        "run": {
            "input_dir": summary.input_dir, "output_dir": summary.output_dir,
            "started_at": summary.started_at, "finished_at": summary.finished_at,
            "duration_seconds": summary.duration_s, "parser": summary.parser_version,
        },
        "totals": {
            "total_files": summary.total,
            "successful": summary.count("success"),
            "failed": summary.count("failed"),
            "skipped_unchanged": summary.count("skipped"),
            "skipped_unsupported": len(summary.unsupported),
            "source_missing": len(summary.missing_sources),
        },
        "file_types": dict(by_type),
        "file_type_status": {k: dict(v) for k, v in per_status_type.items()},
        "department_counts": dict(by_dept),
        "validation": {
            "status_counts": dict(validations),
            "mean_word_recall": round(sum(recalls) / len(recalls), 4) if recalls else None,
            "mean_number_recall": round(sum(nrecalls) / len(nrecalls), 4) if nrecalls else None,
        },
        "errors": [{"path": r.source_path, "error": r.reason} for r in results if r.status == "failed"],
        "warnings": [{"path": r.source_path, "warnings": r.warnings} for r in results if r.warnings],
        "unsupported_files": summary.unsupported,
        "missing_sources": summary.missing_sources,
        "documents": [
            {
                "path": r.source_path, "department": r.department, "type": r.file_type, "status": r.status,
                "validation": r.validation_status, "pages_or_sheets": r.page_count, "chars": r.char_count,
                "word_recall": r.word_recall, "number_recall": r.number_recall, "seconds": r.duration_s,
                "note": r.reason if r.status != "success" else "",
            }
            for r in results
        ],
        "corpus_snapshot": corpus,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1%}" if value <= 1 else f"{value:.1f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    t, run, val = report["totals"], report["run"], report["validation"]
    lines = [
        "# Parsing report", "",
        f"Generated: {report['generated_at']}  ",
        f"Parser: {run['parser']}  ",
        f"Input: `{run['input_dir']}` -> Output: `{run['output_dir']}`  ",
        f"Duration: {run['duration_seconds']} s", "",
        "## Totals (this run)", "",
        "| Metric | Count |", "|---|---|",
        f"| Files discovered | {t['total_files']} |",
        f"| Successful | {t['successful']} |",
        f"| Failed | {t['failed']} |",
        f"| Skipped (unchanged) | {t['skipped_unchanged']} |",
        f"| Skipped (unsupported type) | {t['skipped_unsupported']} |",
        f"| Source no longer present | {t['source_missing']} |", "",
        "## By file type", "", "| Type | Files |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(report["file_types"].items())], "",
        "## By department", "", "| Department | Files |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(report["department_counts"].items())], "",
        "## Validation", "",
        f"Status counts: {json.dumps(val['status_counts'])}  ",
        f"Mean word recall: {_fmt(val['mean_word_recall'])}  ",
        f"Mean number recall: {_fmt(val['mean_number_recall'])}", "",
        "Recall = share of distinct words/numbers found by an *independent* extractor "
        "(python-docx / openpyxl / pypdfium2) that also appear in the Markdown.", "",
        "## Errors", "",
    ]
    lines += [f"- `{e['path']}`: {e['error']}" for e in report["errors"]] or ["None."]
    lines += ["", "## Warnings", ""]
    lines += [f"- `{w['path']}`: " + " | ".join(w["warnings"]) for w in report["warnings"]] or ["None."]
    if report["unsupported_files"]:
        lines += ["", "## Skipped: unsupported files", ""]
        lines += [f"- `{u['path']}`: {u['reason']}" for u in report["unsupported_files"]]
    lines += ["", "## Per-document results", "",
              "| Document | Dept | Type | Status | Validation | Pages/sheets | Words recall | Numbers recall | Sec |",
              "|---|---|---|---|---|---|---|---|---|"]
    for d in report["documents"]:
        lines.append(
            f"| {d['path']} | {d['department']} | {d['type']} | {d['status']} | {d['validation'] or '-'} | "
            f"{_fmt(d['pages_or_sheets'])} | {_fmt(d['word_recall'])} | {_fmt(d['number_recall'])} | {d['seconds']} |"
        )
    c = report["corpus_snapshot"]
    lines += ["", "## Corpus snapshot (whole manifest)", "",
              f"{c['documents_in_manifest']} documents tracked; {c['successful']} successful, {c['failed']} failed."]
    return "\n".join(lines) + "\n"


def write_report(summary: ParseRunSummary, manifest: Manifest, reports_dir: Path) -> dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(summary, manifest)
    json_path = reports_dir / "parsing_report.json"
    md_path = reports_dir / "parsing_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
