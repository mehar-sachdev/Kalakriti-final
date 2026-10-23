#!/usr/bin/env python
"""Validate the site before packaging (requirement: "programmatically validate every
referenced local image" and check product links/documents are consistent).

    python scripts/validate_site.py                # auto-parses documents/ first if no manifest exists yet
    python scripts/validate_site.py --no-auto-parse # fail instead of parsing (useful in CI)

Checks:
* every product's image file exists on disk (frontend/images/...)
* every product's URL is the expected #product-<id> form
* the region -> city -> craft hierarchy only contains cities/regions that are really
  in the product data (nothing invented)
* every generated document in documents/ was actually parsed successfully (manifest),
  with no missing or duplicate documents against the real corpus on disk
* every product has a corresponding product DOCX in documents/product/
* the frontend HTML references no leftover third-party chatbot widget, and no external
  image URLs outside the documented, deliberate exceptions
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.generate_documents import slug  # noqa: E402 - reuse the real slug function, don't duplicate it

EXPECTED_DOC_COUNTS = {"product": 147, "competitor": 2, "regional": 6, "craft": 9, "artisan": 1}  # product sheets + catalogue workbook
EXPECTED_TOTAL_DOCS = sum(EXPECTED_DOC_COUNTS.values())


def ensure_manifest(problems: list[str], auto_parse: bool) -> dict | None:
    """Return the manifest dict, parsing documents/ for real first if it doesn't exist yet.
    Never fabricates a manifest - either runs the real Docling parse, or reports the gap."""
    manifest_path = ROOT / "data" / "processed" / "manifest.json"
    if not manifest_path.exists():
        if not auto_parse:
            problems.append("data/processed/manifest.json not found - run `python scripts/parse_documents.py` first "
                            "(or re-run without --no-auto-parse).")
            return None
        print("No manifest yet - running the real Docling parse of documents/ first "
              "(python scripts/parse_documents.py)...")
        from backend.config import Settings
        from backend.ingestion.pipeline import parse_documents
        from backend.ingestion.manifest import Manifest
        from backend.ingestion.report import write_report

        settings = Settings(_env_file=None)
        summary = parse_documents(settings, settings.raw_dir, settings.processed_dir)
        write_report(summary, Manifest.load(settings.manifest_path), settings.reports_dir)
        print(f"Parsed: {summary.count('success')} ok, {summary.count('failed')} failed, "
              f"{summary.count('skipped')} unchanged, {len(summary.unsupported)} unsupported.")
        if summary.count("failed"):
            problems.append(f"{summary.count('failed')} document(s) failed to parse during auto-parse: "
                            f"{[r.source_path for r in summary.results if r.status == 'failed']}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-auto-parse", dest="auto_parse", action="store_false")
    args = ap.parse_args()
    problems: list[str] = []

    catalog = json.loads((ROOT / "data" / "metadata" / "products.json").read_text(encoding="utf-8"))
    hierarchy = json.loads((ROOT / "data" / "metadata" / "region_city_craft.json").read_text(encoding="utf-8"))
    frontend = ROOT / "frontend"

    if len(catalog) != 146:
        problems.append(f"Expected 146 products, found {len(catalog)}.")

    for p in catalog:
        if not (frontend / p["image"]).is_file():
            problems.append(f"Missing image file for product {p['product_id']}: {p['image']}")
        if p["url"] != f"#product-{p['product_id']}":
            problems.append(f"Unexpected URL for product {p['product_id']}: {p['url']}")
        doc = ROOT / "documents" / "product" / f"{p['product_id']:02d}_{slug(p['name'])}.docx"
        if not doc.is_file():
            problems.append(f"Missing product document for {p['product_id']}: {doc.relative_to(ROOT)}")

    catalog_pairs = {(p["region"], p["city"]) for p in catalog}
    hierarchy_pairs = {(r["region"], c["city"]) for r in hierarchy for c in r["cities"]}
    if hierarchy_pairs != catalog_pairs:
        problems.append(f"Region/city hierarchy does not match the product catalogue: {hierarchy_pairs ^ catalog_pairs}")

    # --- corpus on disk: exact counts per category, no missing/duplicate files ------------------
    on_disk: dict[str, list[str]] = {}
    for category, expected in EXPECTED_DOC_COUNTS.items():
        files = sorted(p.name for p in (ROOT / "documents" / category).glob("*") if p.is_file())
        on_disk[category] = files
        if len(files) != expected:
            problems.append(f"documents/{category}/ has {len(files)} file(s), expected {expected}: {files}")
        if len(files) != len(set(files)):
            problems.append(f"documents/{category}/ has duplicate filenames.")
    total_on_disk = sum(len(v) for v in on_disk.values())
    if total_on_disk != EXPECTED_TOTAL_DOCS:
        problems.append(f"Total documents on disk is {total_on_disk}, expected {EXPECTED_TOTAL_DOCS}.")

    manifest = ensure_manifest(problems, args.auto_parse)
    if manifest is not None:
        docs = manifest.get("documents", {})
        failed = [d for d in docs.values() if d.get("status") != "success" and not d.get("source_missing")]
        if failed:
            problems.append(f"{len(failed)} document(s) failed to parse: {[d['source_path'] for d in failed]}")
        successful = [d for d in docs.values() if d.get("status") == "success" and not d.get("source_missing")]
        if len(successful) != EXPECTED_TOTAL_DOCS:
            problems.append(f"Manifest has {len(successful)} successfully parsed document(s), expected {EXPECTED_TOTAL_DOCS}.")
        source_paths = [d["source_path"] for d in successful]
        if len(source_paths) != len(set(source_paths)):
            problems.append("Manifest contains duplicate source_path entries.")
        # every product's document must map to a manifest entry whose extracted product_id round-trips
        by_path = {d["source_path"]: d for d in successful}
        for p in catalog:
            rel = f"product/{p['product_id']:02d}_{slug(p['name'])}.docx"
            entry = by_path.get(rel)
            if entry is None:
                problems.append(f"Product {p['product_id']} document not found in manifest: {rel}")
                continue
            extracted_id = (entry.get("metadata") or {}).get("product_id")
            if extracted_id != str(p["product_id"]):
                problems.append(f"Product {p['product_id']} document's extracted product_id metadata is "
                                f"'{extracted_id}', expected '{p['product_id']}' (incorrectly mapped document).")

    index_html = (frontend / "index.html").read_text(encoding="utf-8")
    if "jotform" in index_html.lower():
        problems.append("index.html still references the third-party Jotform widget.")
    if 'http://127.0.0.1:8000' in index_html:
        problems.append("index.html still contains a hard-coded absolute backend URL.")
    if "kaiLauncher" not in index_html:
        problems.append("index.html is missing the Kalakriti AI chat widget.")
    external_images = sorted(set(re.findall(r'https?://[^\s"\')]+\.(?:jpg|jpeg|png|svg|webp|gif)\b', index_html, re.I)))
    if external_images:
        problems.append(f"index.html still references {len(external_images)} external image URL(s): {external_images[:5]}")

    if problems:
        print(f"FAILED: {len(problems)} problem(s) found:\n")
        for p in problems:
            print(" -", p)
        return 1
    print(f"OK: {len(catalog)} products, {len(hierarchy)} regions, all images and documents present, no leftover Jotform widget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
