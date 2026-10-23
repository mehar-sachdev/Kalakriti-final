"""Markdown clean-up and the processed-file format (front matter + body)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PAGE_MARKER_FMT = "<!-- page: {n} -->"
PAGE_MARKER_RE = re.compile(r"^<!--\s*page:\s*(\d+)\s*-->\s*$", re.MULTILINE)
SHEET_HEADING_PREFIX = "Sheet: "

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_NUMBERED_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+([A-Z][^\n]{2,90})$")
_MOJIBAKE_RE = re.compile(r"Ã[\x80-\xbf]|â€|â‚¹|Â\s")


def clean_markdown(markdown: str, *, promote_headings: bool = True) -> tuple[str, dict[str, int]]:
    """Normalise whitespace/encoding artefacts; optionally recover numbered headings."""
    stats = {"headings_promoted": 0}
    text = markdown.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"<!--\s*image\s*-->", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    if promote_headings:
        text, stats["headings_promoted"] = promote_numbered_headings(text)
    return text, stats


def count_headings(markdown: str) -> int:
    return sum(1 for line in markdown.split("\n") if _HEADING_RE.match(line))


def promote_numbered_headings(markdown: str, *, min_existing: int = 3) -> tuple[str, int]:
    """Word files often carry section titles as plain bold paragraphs ("5.1 Business Travel").

    When Docling found fewer than ``min_existing`` real headings, promote short,
    isolated, numbered, capitalised lines to headings so the chunker can follow the
    document's own structure.  Depth follows the numbering (5 -> H2, 5.1 -> H3).
    """
    lines = markdown.split("\n")
    existing = sum(1 for line in lines if (m := _HEADING_RE.match(line)) and len(m.group(1)) >= 2)
    if existing >= min_existing:
        return markdown, 0

    promoted = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "|", "-", "*", "<!--", ">")):
            continue
        prev_blank = i == 0 or not lines[i - 1].strip() or lines[i - 1].lstrip().startswith("<!--")
        next_blank = i == len(lines) - 1 or not lines[i + 1].strip()
        if not (prev_blank and next_blank):
            continue
        unescaped = stripped.replace("\\.", ".")
        match = _NUMBERED_RE.match(unescaped)
        if not match:
            continue
        number, title = match.groups()
        if title.rstrip().endswith((".", ":", ";", ",")) or len(title.split()) > 12:
            continue
        depth = min(number.count(".") + 2, 6)
        lines[i] = f"{'#' * depth} {unescaped}"  # keep the document's own numbering style ("5.1 " / "5. ")
        promoted += 1
    return "\n".join(lines), promoted


def find_encoding_problems(markdown: str) -> dict[str, int]:
    return {
        "replacement_chars": markdown.count("\ufffd"),
        "mojibake": len(_MOJIBAKE_RE.findall(markdown)),
        "control_chars": len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", markdown)),
    }


# --------------------------------------------------------------------------- processed file format
def write_processed_markdown(path: Path, body: str, front_matter: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key, value in front_matter.items():
        if value is None:
            continue
        lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n\n" + body, encoding="utf-8")
    tmp.replace(path)


def read_processed_markdown(path: Path) -> tuple[dict[str, Any], str]:
    """Split a processed file into (front matter dict, markdown body)."""
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    meta: dict[str, Any] = {}
    for line in text[4:end].split("\n"):
        key, _, raw = line.partition(": ")
        if not key:
            continue
        try:
            meta[key] = json.loads(raw)
        except json.JSONDecodeError:
            meta[key] = raw
    return meta, text[end + 5:].lstrip("\n")
