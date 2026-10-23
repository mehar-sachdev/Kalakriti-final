"""Tests for scripts/validate_site.py - the pre-packaging consistency check."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def run_validator(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_site.py"), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )


def test_validator_passes_on_the_real_repository_state():
    """The real corpus, real images and real frontend must validate clean - this is the same
    check run before packaging, so a regression here means the shipped ZIP would be broken."""
    result = run_validator()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK:" in result.stdout
    assert "146 products" in result.stdout and "6 regions" in result.stdout


def test_validator_auto_parses_when_manifest_is_missing(tmp_path):
    """Requirement: never fabricate a manifest - either really parse, or say so and fail."""
    manifest = ROOT / "data" / "processed" / "manifest.json"
    backup = None
    if manifest.exists():
        backup = manifest.read_bytes()
        manifest.unlink()
    try:
        result = run_validator()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "running the real Docling parse" in result.stdout
        assert "165 ok" in result.stdout or "Parsed: 165" in result.stdout
        assert manifest.exists()  # a real manifest was written, not faked
        data = json.loads(manifest.read_text())
        assert len(data["documents"]) == 165
    finally:
        if backup is not None:
            manifest.write_bytes(backup)


def test_validator_no_auto_parse_fails_honestly_when_manifest_missing():
    manifest = ROOT / "data" / "processed" / "manifest.json"
    backup = manifest.read_bytes() if manifest.exists() else None
    if manifest.exists():
        manifest.unlink()
    try:
        result = run_validator("--no-auto-parse")
        assert result.returncode == 1
        assert "manifest.json not found" in result.stdout
    finally:
        if backup is not None:
            manifest.write_bytes(backup)


def test_no_external_image_urls_in_frontend():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    import re

    urls = re.findall(r'https?://[^\s"\')]+\.(?:jpg|jpeg|png|svg|webp|gif)\b', html, re.I)
    assert urls == []


def test_contact_roster_uses_only_the_requested_names_and_user_supplied_phone():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "<h3>Mehar</h3><p>+91 98765 43210</p>" in html
    assert "<h3>Nandini</h3><p>+91 87654 32109</p>" in html
    assert "<h3>Aditi Agarawal</h3><p>+91 8762078901</p>" in html
    assert "<h3>Mahi</h3>" not in html and "<h3>Yashi</h3>" not in html and "<h3>Yahi</h3>" not in html


def test_document_corpus_counts_match_the_brief():
    counts = {p.name: len(list((ROOT / "documents" / p.name).glob("*")))
              for p in (ROOT / "documents").iterdir() if p.is_dir()}
    assert counts == {"product": 147, "competitor": 2, "regional": 6, "craft": 9, "artisan": 1}
    assert sum(counts.values()) == 165
