import pytest

from backend.exceptions import ParsingError
from backend.ingestion.discovery import UNASSIGNED_DEPARTMENT, discover_documents, make_document_id, slugify
from pathlib import Path


@pytest.mark.parametrize("name,slug", [
    ("Sales & Customer", "sales-and-customer"), ("Legal & Compliance", "legal-and-compliance"),
    ("HR", "hr"), ("  Operations   &  Logistics ", "operations-and-logistics"), ("Café/Ünïcode", "cafe-unicode"), ("!!!", "unnamed"),
])
def test_slugify(name, slug):
    assert slugify(name) == slug


def test_departments_are_discovered_dynamically(corpus):
    result = discover_documents(corpus)
    assert result.departments == {"Finance": 4, "Sales & Customer": 2, "Legal & Compliance": 1}  # broken+empty+docx+txt in Finance


def test_new_department_needs_no_code_change(corpus):
    (corpus / "Brand New Dept").mkdir()
    (corpus / "Brand New Dept" / "a.txt").write_text("hello")
    result = discover_documents(corpus)
    assert "Brand New Dept" in result.departments
    assert {d.department_slug for d in result.documents} >= {"brand-new-dept"}


def test_unsupported_and_temp_files_are_skipped_not_fatal(corpus):
    (corpus / "Finance" / "~$lock.docx").write_bytes(b"x")
    (corpus / "Finance" / ".DS_Store").write_bytes(b"x")
    result = discover_documents(corpus)
    assert [s["path"] for s in result.skipped] == ["Finance/drawing.dwg"]
    assert not any("~$" in d.filename or d.filename.startswith(".") for d in result.documents)


def test_department_filter_by_name_or_slug(corpus):
    assert {d.department_slug for d in discover_documents(corpus, department="sales-and-customer").documents} == {"sales-and-customer"}
    assert len(discover_documents(corpus, department="FINANCE").documents) == 4
    assert discover_documents(corpus, department="nope").documents == []


def test_nested_folders_are_included(corpus):
    docs = discover_documents(corpus, department="Legal & Compliance").documents
    assert [d.relative_path for d in docs] == ["Legal & Compliance/Contracts/vendor_terms.md"]


def test_loose_files_go_to_unassigned(tmp_path):
    (tmp_path / "loose.txt").write_text("x")
    docs = discover_documents(tmp_path).documents
    assert docs[0].department_name == UNASSIGNED_DEPARTMENT


def test_document_id_is_stable_and_unique_per_extension():
    a = make_document_id("finance", Path("09_Policy.pdf"))
    b = make_document_id("finance", Path("09_Policy.docx"))
    assert a == "finance__09-policy-pdf" and a != b
    assert make_document_id("finance", Path("09_Policy.pdf")) == a


def test_checksum_changes_with_content(corpus):
    before = {d.document_id: d.checksum for d in discover_documents(corpus).documents}
    (corpus / "Finance" / "notes.txt").write_text("changed")
    after = {d.document_id: d.checksum for d in discover_documents(corpus).documents}
    changed = [k for k in before if before[k] != after[k]]
    assert changed == ["finance__notes-txt"]


def test_missing_input_dir_gives_actionable_error(tmp_path):
    with pytest.raises(ParsingError) as exc:
        discover_documents(tmp_path / "nowhere")
    assert "data/raw" in exc.value.hint
