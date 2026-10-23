"""Recursive, dynamic discovery of source documents.

Departments are *not* hard-coded: every immediate sub-folder of the input
directory is a department, whatever it is called.  Adding a new department is
just adding a folder.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from backend.exceptions import ParsingError
from backend.models.documents import SourceDocument

logger = logging.getLogger(__name__)

# Extending support = add the extension here and register a parser in parser.py.
SUPPORTED_EXTENSIONS = {"pdf", "docx", "xlsx", "xls", "csv", "txt", "md"}
IGNORED_DIR_NAMES = {"processed", "__pycache__", "node_modules"}
UNASSIGNED_DEPARTMENT = "Unassigned"


def slugify(text: str) -> str:
    """'Sales & Customer' -> 'sales-and-customer'.  Safe for URLs and SQL filters."""
    text = text.replace("&", " and ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "unnamed"


def make_document_id(department_slug: str, path_within_department: Path) -> str:
    """Stable id derived from the location, so an edited file keeps its id."""
    ext = path_within_department.suffix.lstrip(".").lower()
    stem_path = path_within_department.with_suffix("").as_posix()
    return f"{department_slug}__{slugify(stem_path)}-{ext}"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class DiscoveryResult:
    documents: list[SourceDocument] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    @property
    def departments(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for doc in self.documents:
            counts[doc.department_name] = counts.get(doc.department_name, 0) + 1
        return counts


def _is_hidden_or_temp(path: Path) -> bool:
    name = path.name
    return name.startswith(".") or name.startswith("~$") or name.lower() in {"thumbs.db", "desktop.ini"}


def discover_documents(
    input_dir: Path,
    department: str | None = None,
    extensions: set[str] | None = None,
) -> DiscoveryResult:
    """Find supported files under ``input_dir/<department>/**``."""
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise ParsingError(
            f"Input directory not found: {input_dir}",
            hint="Place the department folders under data/raw/ (e.g. data/raw/Finance/policy.pdf).",
        )
    extensions = extensions or SUPPORTED_EXTENSIONS
    wanted = department.strip().lower() if department else None
    result = DiscoveryResult()

    entries = sorted(input_dir.iterdir(), key=lambda p: p.name.lower())
    department_dirs = [
        p for p in entries if p.is_dir() and not p.name.startswith(".") and p.name.lower() not in IGNORED_DIR_NAMES
    ]
    loose_files = [p for p in entries if p.is_file() and not _is_hidden_or_temp(p)]

    def handle_file(path: Path, dept_name: str, base: Path) -> None:
        if _is_hidden_or_temp(path):
            return
        ext = path.suffix.lstrip(".").lower()
        rel_posix = path.relative_to(input_dir).as_posix()
        if ext not in extensions:
            result.skipped.append({"path": rel_posix, "reason": f"unsupported file type '.{ext}'" if ext else "no extension"})
            logger.info("Skipping unsupported file %s", rel_posix)
            return
        slug = slugify(dept_name)
        result.documents.append(
            SourceDocument(
                path=path,
                relative_path=rel_posix,
                department_name=dept_name,
                department_slug=slug,
                file_type=ext,
                size_bytes=path.stat().st_size,
                checksum=sha256_file(path),
                document_id=make_document_id(slug, path.relative_to(base)),
            )
        )

    for dept_dir in department_dirs:
        name = dept_dir.name
        if wanted and wanted not in {name.lower(), slugify(name)}:
            continue
        for path in sorted(p for p in dept_dir.rglob("*") if p.is_file()):
            handle_file(path, name, dept_dir)

    if loose_files and (wanted is None or wanted in {UNASSIGNED_DEPARTMENT.lower(), slugify(UNASSIGNED_DEPARTMENT)}):
        logger.warning(
            "%d file(s) sit directly in %s without a department folder; filing them under '%s'.",
            len(loose_files), input_dir, UNASSIGNED_DEPARTMENT,
        )
        for path in loose_files:
            handle_file(path, UNASSIGNED_DEPARTMENT, input_dir)

    if wanted and not result.documents:
        logger.warning("No documents found for department '%s' under %s", department, input_dir)

    logger.info("Found %d documents in %d departments", len(result.documents), len(result.departments))
    return result
