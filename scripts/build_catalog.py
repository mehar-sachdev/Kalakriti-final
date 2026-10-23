"""Build the single authoritative product catalog: data/metadata/products.json.

Source of truth: the 60-product array embedded in the original Kalakriti storefront
(frontend/index_backup.html in the uploaded project, extracted once into
scripts/_source_products.json so this script has no dependency on a specific HTML
snapshot). Everything downstream (RAG documents, the /products API fallback, the
front-end product cards) reads from data/metadata/products.json, so there is exactly
one version of each product's facts.

Fixes applied to the original data:
* Image path: the previous seed_database.py recomputed the image filename by
  slugifying the product name, which was wrong for 9/60 products (e.g. product 2
  "Chikankari Embroidered Kurta" vs the actual file "2_chikankari_kurta.jpg"). This
  script instead maps each product id to its REAL file on disk under frontend/images/,
  which is the only reliable source.
* City: derived from the existing "origin" field ("Varanasi, Uttar Pradesh" -> city
  "Varanasi"). No city is invented; only origins already present in the data are used.
* Competitor reference price: a clearly-labelled, deterministic ILLUSTRATIVE figure
  (see documents/competitor/methodology_note.docx). Never presented as real market data.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_IMAGES = ROOT / "frontend" / "images"
SOURCE_PRODUCTS = ROOT / "scripts" / "_source_products.json"
SOURCE_UPDATES = ROOT / "scripts" / "_source_catalog_updates.json"
OUT = ROOT / "data" / "metadata" / "products.json"

# Deterministic illustrative competitor multiplier per craft category, chosen once and
# documented — NOT fitted to any real market data. Clearly labelled everywhere it is used.
COMPETITOR_MULTIPLIER = {
    "Textile": 1.28, "Pottery": 1.35, "Metalwork": 1.22, "Woodwork": 1.30,
    "Jewellery": 1.40, "Leatherwork": 1.25, "Painting": 1.45, "Papier-mâché": 1.33,
}

REGION_SLUG_OVERRIDE = {"Jammu & Kashmir": "Jammu_Kashmir"}


def region_folder(region: str) -> str:
    return REGION_SLUG_OVERRIDE.get(region, region.replace(" ", "_").replace("&", ""))


def slugify(text: str) -> str:
    text = text.replace("&", " and ")
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()


def build_image_map() -> dict[int, str]:
    """id -> path relative to frontend/, taken from the REAL files on disk."""
    mapping: dict[int, str] = {}
    for region_dir in sorted(p for p in FRONTEND_IMAGES.iterdir() if p.is_dir()):
        image_files = sorted(region_dir.glob("*.jpg")) + sorted(region_dir.glob("*.svg"))
        for f in image_files:
            prefix = f.name.split("_", 1)[0]
            if not prefix.isdigit():
                continue
            pid = int(prefix)
            mapping[pid] = f"images/{region_dir.name}/{f.name}"
    return mapping


def _svg_demo_image(product: dict, relative_path: str) -> None:
    """Write a local, product-specific vector illustration (see scripts/product_art.py).

    The artwork is chosen from the product's own name/craft/city/material, so a plate is
    drawn as a plate, a bangle set as bangles, a Madhubani fish painting with fish, etc.
    """
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from product_art import render_svg

    item = {**product, "city": product.get("city") or clean_city(product["origin"])}
    (ROOT / "frontend" / relative_path).write_text(render_svg(item), encoding="utf-8")


# Verified photo matches. Some of the original KALAKRITI product photos were saved under the
# wrong product's filename (e.g. the file named "45_shantiniketan_leather_notebook.jpg" is a
# Dokra brass figure). Each photo below was checked visually against the product's name,
# craft and region label, and copied under the CORRECT product's name into images/<Region>/
# photos/. Products without a genuinely matching photo use a generated illustration instead.
PHOTO_MATCHES = {
    17: "images/Jammu_Kashmir/photos/17_walnut_wood_jewellery_box.jpg",
    18: "images/Jammu_Kashmir/photos/18_kashmiri_crewel_cushion_cover.jpg",
    33: "images/Rajasthan/photos/33_rajasthani_blue_pottery_vase.jpg",
    34: "images/Rajasthan/photos/34_sanganer_floral_print_saree.jpg",
    36: "images/Rajasthan/photos/36_kundan_inspired_jewellery_box.jpg",
    41: "images/West_Bengal/photos/41_bengal_kantha_wall_textile.jpg",
    42: "images/West_Bengal/photos/42_dokra_brass_figurine.jpg",
    44: "images/West_Bengal/photos/44_baluchari_silk_saree.jpg",
    50: "images/West_Bengal/photos/50_dokra_tribal_lamp.jpg",
    52: "images/Bihar/photos/52_sikki_grass_decorative_basket.jpg",
    53: "images/Bihar/photos/53_sujuni_embroidered_textile.jpg",
    55: "images/Bihar/photos/55_madhubani_fish_motif_artwork.jpg",
    59: "images/Bihar/photos/59_bhagalpur_tussar_silk_stole.jpg",
}
# Original products whose existing photo shows a different item and no correct photo exists.
ILLUSTRATE_IDS = {13, 15, 19}


def clean_city(origin: str) -> str:
    city = origin.split(",")[0].strip()
    return re.sub(r"\s+region$", "", city, flags=re.I)  # "Shantiniketan region" -> "Shantiniketan"


def main() -> None:
    source = json.loads(SOURCE_PRODUCTS.read_text(encoding="utf-8"))
    updates = json.loads(SOURCE_UPDATES.read_text(encoding="utf-8"))
    overrides = updates.get("overrides", {})
    source = [{**product, **overrides.get(str(product["id"]), {})} for product in source]
    for product in source:
        if product.get("city"):
            product["origin"] = f"{product['city']}, {product['region']}"
    for product_id, product in enumerate(updates.get("additions", []), start=61):
        product["id"] = product_id
        product["origin"] = f"{product['city']}, {product['region']}"
        product["artisan"] = "Kalakriti Academic Demo Studio"
        product["rating"] = 4.7
        product["academic_demo"] = True
        source.append(product)
    demo_regions = {"Rajasthan", "West Bengal", "Bihar"}
    for product in source:
        if product.get("academic_demo") or product["region"] in demo_regions or product["id"] in ILLUSTRATE_IDS:
            image_path = f"images/{region_folder(product['region'])}/{product['id']:03d}_demo.svg"
            _svg_demo_image(product, image_path)
            product["image"] = image_path
    # The storefront's six region tiles share the matching product's local generated image.
    for product_id in (31, 41, 51):
        product = next(p for p in source if p["id"] == product_id)
        relative_path = f"images/{region_folder(product['region'])}/{product_id:03d}_demo.svg"
        _svg_demo_image(product, relative_path)
    image_map = build_image_map()
    for product_id, photo in PHOTO_MATCHES.items():
        if not (ROOT / "frontend" / photo).is_file():
            raise SystemExit(f"FATAL: verified photo missing for product {product_id}: {photo}")
        image_map[product_id] = photo
    missing = [p["id"] for p in source if p["id"] not in image_map]
    if missing:
        raise SystemExit(f"FATAL: no image file found on disk for product id(s) {missing}")

    catalog = []
    for p in source:
        craft = p["craft"]
        # Existing catalogue reference figures remain explicitly illustrative. New demo items
        # have no fabricated competitor price; live web research is a separate runtime feature.
        competitor_price = (
            round(p["price"] * COMPETITOR_MULTIPLIER.get(craft, 1.30) / 10) * 10
            if not p.get("academic_demo") else None
        )
        item = {
            "product_id": p["id"],
            "name": p["name"],
            "category": craft,                       # craft category (Textile, Pottery, ...)
            "craft": craft,
            "region": p["region"],
            "region_slug": slugify(p["region"]),
            "city": p.get("city") or clean_city(p["origin"]),
            "origin": f"{p.get('city') or clean_city(p['origin'])}, {p['region']}",
            "artisan": p["artisan"],
            "material": p["material"],
            "technique": p["technique"],
            "description": p.get("description", ""),
            "price_inr": p["price"],
            "rating": p["rating"],
            "competitor_price_inr": competitor_price,
            "competitor_price_is_illustrative": competitor_price is not None,
            "competitor_price_difference_inr": competitor_price - p["price"] if competitor_price is not None else None,
            "competitor_price_difference_pct": round((competitor_price - p["price"]) / p["price"] * 100, 1) if competitor_price is not None else None,
            "availability": "Academic demo" if p.get("academic_demo") else "In stock",
            "image": image_map[p["id"]],               # relative to frontend/, e.g. images/Bihar/51_....jpg
            "url": f"#product-{p['id']}",              # stable in-page route, opens the product modal
        }
        if p.get("academic_demo") or p["region"] in demo_regions:
            item["description"] = (
                f"{p['name']} is an academic/demo catalogue concept representing {craft.lower()} "
                f"associated with {p['city']}, {p['region']}. It is made in this demonstration from "
                f"{p['material']} using {p['technique']}. Its listing price is a project demonstration "
                "value, not a verified marketplace quote; this local illustration is original to the project."
            )
        catalog.append(item)
    catalog.sort(key=lambda x: x["product_id"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(catalog)} products to {OUT}")

    regions: dict[str, dict] = {}
    for p in catalog:
        r = regions.setdefault(p["region"], {"region": p["region"], "region_slug": p["region_slug"], "cities": {}})
        c = r["cities"].setdefault(p["city"], {"city": p["city"], "crafts": set(), "product_ids": []})
        c["crafts"].add(p["craft"])
        c["product_ids"].append(p["product_id"])
    for r in regions.values():
        for c in r["cities"].values():
            c["crafts"] = sorted(c["crafts"])
        r["cities"] = sorted(r["cities"].values(), key=lambda c: c["city"])
    hierarchy = sorted(regions.values(), key=lambda r: r["region"])
    (ROOT / "data" / "metadata" / "region_city_craft.json").write_text(
        json.dumps(hierarchy, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote region -> city -> craft hierarchy for {len(hierarchy)} regions")


if __name__ == "__main__":
    main()
