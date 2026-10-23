import json
import shutil

import pytest

pytest.importorskip("docling")

from backend.ingestion.manifest import Manifest
from backend.ingestion.pipeline import parse_documents, processed_relpath
from backend.ingestion.report import build_report, render_markdown, write_report
from backend.ingestion.markdown_utils import read_processed_markdown


def run(settings, corpus, registry, **kw):
    return parse_documents(settings, corpus, settings.processed_dir, registry=registry, **kw)


@pytest.mark.docling
def test_one_bad_file_never_stops_the_batch(settings, corpus, offline_registry):
    summary = run(settings, corpus, offline_registry)
    by_name = {r.source_path: r for r in summary.results}
    assert by_name["Finance/broken.docx"].status == "failed"
    assert by_name["Finance/empty.txt"].status == "failed" and "empty" in by_name["Finance/empty.txt"].reason.lower()
    good = [r for r in summary.results if r.status == "success"]
    assert {r.source_path for r in good} == {
        "Finance/09_Fixture_Expense_Policy.docx", "Finance/notes.txt", "Sales & Customer/TST-SAL-XLSX-002A_Fixture_Matrix.xlsx",
        "Sales & Customer/12_Fixture_Return_Policy.pdf", "Legal & Compliance/Contracts/vendor_terms.md"}
    assert [u["path"] for u in summary.unsupported] == ["Finance/drawing.dwg"]


@pytest.mark.docling
def test_manifest_records_everything_needed(settings, corpus, offline_registry):
    run(settings, corpus, offline_registry)
    m = Manifest.load(settings.manifest_path)
    entry = m.get("finance__09-fixture-expense-policy-docx")
    for key in ("checksum_sha256", "processing_timestamp", "parser", "parser_version", "status", "processed_path",
                "validation", "metadata", "department", "department_slug", "source_path"):
        assert key in entry, key
    assert entry["status"] == "success" and entry["metadata"]["doc_code"] == "TST-FIN-POL-001"
    assert entry["metadata"]["status"] == "Active" and entry["metadata"]["version"] == "1.1"
    assert m.get("finance__broken-docx")["status"] == "failed" and m.get("finance__broken-docx")["error"]
    assert settings.manifest_path.with_suffix(".csv").exists()


@pytest.mark.docling
def test_processed_files_are_organised_by_department_with_front_matter(settings, corpus, offline_registry):
    run(settings, corpus, offline_registry)
    path = settings.processed_dir / "sales-and-customer" / "TST-SAL-XLSX-002A_Fixture_Matrix.xlsx.md"
    meta, body = read_processed_markdown(path)
    assert meta["department"] == "Sales & Customer" and meta["file_type"] == "xlsx" and "## Sheet: Approval Rules" in body
    assert (settings.processed_dir / "legal-and-compliance" / "Contracts" / "vendor_terms.md.md").exists()


@pytest.mark.docling
def test_second_run_is_idempotent(settings, corpus, offline_registry):
    run(settings, corpus, offline_registry)
    second = run(settings, corpus, offline_registry)
    assert second.count("success") == 0 and second.count("skipped") == 5
    assert second.count("failed") == 2  # broken files are retried, not silently forgotten


@pytest.mark.docling
def test_changed_file_is_reprocessed_and_force_redoes_all(settings, corpus, offline_registry):
    run(settings, corpus, offline_registry)
    (corpus / "Finance" / "notes.txt").write_text("Changed content about claims within 60 days.")
    again = run(settings, corpus, offline_registry)
    assert [r.source_path for r in again.results if r.status == "success"] == ["Finance/notes.txt"]
    forced = run(settings, corpus, offline_registry, force=True)
    assert forced.count("success") == 5


@pytest.mark.docling
def test_deleted_output_triggers_reprocessing(settings, corpus, offline_registry):
    run(settings, corpus, offline_registry)
    (settings.processed_dir / "finance" / "notes.txt.md").unlink()
    again = run(settings, corpus, offline_registry)
    assert [r.source_path for r in again.results if r.status == "success"] == ["Finance/notes.txt"]


@pytest.mark.docling
def test_changed_parser_configuration_triggers_reprocessing(settings, make_settings, corpus, offline_registry):
    from backend.ingestion.parser import ParserRegistry

    run(settings, corpus, offline_registry)
    other = make_settings(promote_numbered_headings=False)
    again = parse_documents(other, corpus, other.processed_dir, registry=ParserRegistry(other))
    assert again.count("success") == 5


@pytest.mark.docling
def test_removed_source_is_reported(settings, corpus, offline_registry):
    run(settings, corpus, offline_registry)
    (corpus / "Finance" / "notes.txt").unlink()
    again = run(settings, corpus, offline_registry)
    assert again.missing_sources == ["finance__notes-txt"]


@pytest.mark.docling
def test_department_filter_only_touches_that_department(settings, corpus, offline_registry):
    summary = run(settings, corpus, offline_registry, department="legal-and-compliance")
    assert [r.department for r in summary.results] == ["Legal & Compliance"]


@pytest.mark.docling
def test_report_contains_totals_types_departments_errors(settings, corpus, offline_registry):
    summary = run(settings, corpus, offline_registry)
    report = build_report(summary, Manifest.load(settings.manifest_path))
    assert report["totals"] == {"total_files": 7, "successful": 5, "failed": 2, "skipped_unchanged": 0, "skipped_unsupported": 1, "source_missing": 0}
    assert report["file_types"]["docx"] == 2 and report["department_counts"]["Finance"] == 4
    assert {e["path"] for e in report["errors"]} == {"Finance/broken.docx", "Finance/empty.txt"}
    paths = write_report(summary, Manifest.load(settings.manifest_path), settings.reports_dir)
    assert json.loads(paths["json"].read_text())["totals"]["failed"] == 2
    assert "Parsing report" in render_markdown(report) and "broken.docx" in paths["markdown"].read_text()


@pytest.mark.docling
def test_recovered_headings_and_no_encoding_damage(settings, corpus, offline_registry):
    run(settings, corpus, offline_registry)
    _, body = read_processed_markdown(settings.processed_dir / "finance" / "09_Fixture_Expense_Policy.docx.md")
    assert "## 1. Purpose" in body and "### 5.1 Business Travel" in body
    assert "\ufffd" not in body and "â‚¹" not in body


def test_processed_relpath_layout(corpus):
    from backend.ingestion.discovery import discover_documents

    docs = {d.filename: d for d in discover_documents(corpus).documents}
    assert processed_relpath(docs["notes.txt"]) == "finance/notes.txt.md"
