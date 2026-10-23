"""Plain data containers shared by the ingestion and indexing stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceDocument:
    """A source file discovered under ``data/raw/<department>/``."""

    path: Path
    relative_path: str          # POSIX path relative to the input dir, e.g. "Finance/09_Expense.docx"
    department_name: str        # folder name as written, e.g. "Sales & Customer"
    department_slug: str        # url/filter-safe form, e.g. "sales-and-customer"
    file_type: str              # lower-case extension without dot
    size_bytes: int
    checksum: str               # sha256 of file bytes
    document_id: str            # stable id derived from the relative path

    @property
    def filename(self) -> str:
        return self.path.name


@dataclass
class ParsedDocument:
    """Output of a parser."""

    markdown: str
    parser: str
    parser_version: str
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    sheets: list[str] = field(default_factory=list)


@dataclass
class ValidationIssue:
    level: str                  # "error" | "warning" | "info"
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "code": self.code, "message": self.message}


@dataclass
class ValidationResult:
    status: str = "ok"          # ok | warning | error
    issues: list[ValidationIssue] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add(self, level: str, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(level, code, message))
        if level == "error":
            self.status = "error"
        elif level == "warning" and self.status == "ok":
            self.status = "warning"

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "issues": [i.to_dict() for i in self.issues], "stats": self.stats}
