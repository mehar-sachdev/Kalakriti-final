#!/usr/bin/env python
"""Seed a Supabase project's products/orders schema from the authoritative local catalogue.

This is the original project's seeding approach, corrected: the original script recomputed each
product's image filename by slugifying the product name, which was wrong for 9 of 60 products
(the real files on disk don't always match a slugified name exactly - see
scripts/build_catalog.py). This version uses the image path already resolved in
data/metadata/products.json, which was built from the real files on disk, so every row is correct.

Needs SUPABASE_URL and SUPABASE_KEY in .env, and a `products`/`artisans` schema already created in
that Supabase project (this project does not create those tables for you - it only manages its own
separate RAG vector schema; see docs/architecture.md for why the two are kept apart).

    python scripts/seed_database.py            # insert artisans, then products
    python scripts/seed_database.py --dry-run  # show what would be inserted, without writing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from backend.config import get_settings
    from backend.logging_config import redact

    settings = get_settings()
    if settings.supabase_url is None or settings.supabase_key is None:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in .env to seed a Supabase project.", file=sys.stderr)
        print("(The site itself does not need this - it falls back to the local catalogue automatically.)", file=sys.stderr)
        return 2

    catalog = json.loads((ROOT / "data" / "metadata" / "products.json").read_text(encoding="utf-8"))

    artisans: dict[str, dict] = {}
    for p in catalog:
        if p["artisan"] not in artisans:
            artisans[p["artisan"]] = {
                "artisan_id": f"ART{len(artisans) + 1:03d}", "artisan_name": p["artisan"], "craft": p["craft"],
                "state": p["region"], "experience_years": 10, "rating": p["rating"], "payment_status": "Pending",
            }
    artisan_rows = list(artisans.values())

    product_rows = [{
        "product_id": p["product_id"], "product_name": p["name"], "region": p["region"], "craft": p["craft"],
        "material": p["material"], "technique": p["technique"], "origin": p["origin"],
        "artisan_id": artisans[p["artisan"]]["artisan_id"], "price": p["price_inr"], "rating": p["rating"],
        "stock_quantity": 10, "image_url": p["image"], "description": p["description"], "status": "Active",
    } for p in catalog]

    print(f"{len(artisan_rows)} artisans, {len(product_rows)} products ready to insert.")
    if args.dry_run:
        print(json.dumps(product_rows[0], indent=2, ensure_ascii=False))
        return 0

    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_key.get_secret_value())
    try:
        client.table("artisans").insert(artisan_rows).execute()
        print("Artisans inserted.")
        client.table("products").insert(product_rows).execute()
        print("Products inserted.")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {redact(str(exc))[:300]}", file=sys.stderr)
        print("HINT: the 'products'/'artisans' tables must already exist in this Supabase project "
              "(this script inserts rows, it does not create tables).", file=sys.stderr)
        return 2
    print("Done. GET /products will now read these rows from Supabase (with image paths self-healed either way).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
