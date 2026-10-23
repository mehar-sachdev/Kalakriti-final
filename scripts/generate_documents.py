"""Generate the RAG document corpus from data/metadata/products.json.

Produces real PDF/DOCX/XLSX files under documents/ — nothing is fed to the RAG pipeline
as a Python string. Re-running this script regenerates the corpus deterministically from
the same source data (idempotent in content, not in file mtimes).

    documents/product/     one DOCX per product (60) + products_catalog.xlsx (all 60 rows)
    documents/competitor/  competitor_pricing.xlsx + methodology_note.docx (disclaimer)
    documents/regional/    one DOCX per region (6), each listing its cities and crafts
    documents/craft/       one DOCX per craft category (8), technique + associated regions
    documents/artisan/     artisans_directory.xlsx (unique artisans derived from products)

Every document that carries facts opens with a small header table (Product ID / Region /
City / Craft / ...), in the same style the ingestion pipeline's metadata extractor already
recognises, so product_id/region/city/craft become searchable, filterable chunk metadata
with no changes needed to the parser.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import docx
import openpyxl
from docx.shared import Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "documents"
CATALOG = json.loads((ROOT / "data" / "metadata" / "products.json").read_text(encoding="utf-8"))
HIERARCHY = json.loads((ROOT / "data" / "metadata" / "region_city_craft.json").read_text(encoding="utf-8"))

MAROON = RGBColor(0x5B, 0x17, 0x25)

CRAFT_NOTES = {
    "Textile": "Handwoven and hand-printed cloth traditions: silk and cotton weaving, block printing, "
               "tie-dye (bandhani), embroidery and appliqué, practised on pit looms and frame looms passed "
               "down within weaving families and cooperatives.",
    "Pottery": "Wheel-thrown and hand-built clay work, including the distinctive low-fired 'blue pottery' "
               "technique that uses a quartz-and-glaze body rather than clay, and unglazed terracotta work.",
    "Metalwork": "Cast and hammered metal craft in brass, bell-metal and copper, including the lost-wax "
                 "'dokra' casting method and repoussé (hammered relief) decoration.",
    "Woodwork": "Carved and inlaid woodwork in walnut, sheesham and other regional timbers, including "
                "openwork (jali) carving and small lacquered turned items.",
    "Jewellery": "Traditional ornament-making including kundan-style stone setting, thewa (glass and gold "
                 "foil) work, and lac (resin) bangle craft.",
    "Leatherwork": "Hand-stitched leather footwear and goods, notably mojari/jutti slip-on footwear with "
                   "embroidered or block-printed uppers.",
    "Painting": "Narrative folk painting traditions using natural pigments and fine linework, including "
               "Madhubani/Mithila painting and Kalighat-style figurative work.",
    "Papier-mâché": "Layered paper-pulp craft moulded over forms, dried, and finished with fine hand-painted "
                    "gold and floral surface decoration.",
    "Basketry": "Hand-coiled and hand-woven containers and household forms made from regionally available "
                 "plant fibres such as sikki grass, moonj and jute.",
}
REGION_NOTES = {
    "Uttar Pradesh": "Home to Varanasi's silk-weaving and brocade tradition, Lucknow's chikankari "
                     "embroidery, and metal and wood craft centred on Moradabad, Saharanpur and Mathura.",
    "Jammu & Kashmir": "Known for pashmina and kani weaving, walnut wood carving, papier-mâché and Sozni "
                       "embroidery, concentrated around the Kashmir Valley and Srinagar.",
    "Gujarat": "A textile- and craft-dense state: Kutch embroidery and mirrorwork, Bandhani tie-dye, "
              "Ajrakh block printing, Patola weaving and Rogan painting.",
    "Rajasthan": "Blue pottery and block printing around Jaipur and Sanganer, Bagru's hand block printing, "
                "Kota's woven textiles, and Pratapgarh's thewa jewellery work.",
    "West Bengal": "Kantha embroidery, Bishnupur's terracotta and Baluchari silk weaving, Bikna's dokra "
                  "metal casting, and folk art associated with Kolkata and Shantiniketan.",
    "Bihar": "Madhubani (Mithila) painting centred on Madhubani and Darbhanga, Bhagalpur's tussar silk, "
            "and sikki grass and sujuni textile crafts from the wider North Bihar region.",
}


# --------------------------------------------------------------------------- helpers
def header_table(doc: docx.document.Document, rows: list[tuple[str, str]]) -> None:
    table = doc.add_table(rows=len(rows), cols=2)
    table.style = "Table Grid"
    for i, (label, value) in enumerate(rows):
        table.cell(i, 0).text, table.cell(i, 1).text = label, str(value)
        table.cell(i, 0).paragraphs[0].runs[0].bold = True


def title(doc: docx.document.Document, text: str) -> None:
    h = doc.add_heading(text, level=0)
    for run in h.runs:
        run.font.color.rgb = MAROON


def para(doc: docx.document.Document, text: str) -> None:
    doc.add_paragraph(text)


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# --------------------------------------------------------------------------- product/*.docx
def make_product_doc(p: dict, out_dir: Path) -> None:
    doc = docx.Document()
    title(doc, p["name"])
    header_table(doc, [
        ("Product ID", p["product_id"]), ("Category", p["category"]), ("Craft Type", p["craft"]),
        ("Region", p["region"]), ("City", p["city"]), ("Artisan", p["artisan"]),
        ("Material", p["material"]), ("Technique", p["technique"]),
        ("Price (INR)", f"\u20b9{p['price_inr']:,}"), ("Rating", f"{p['rating']} / 5"),
        ("Availability", p["availability"]), ("Product URL", p["url"]),
    ])
    doc.add_heading("1. Description", level=1)
    para(doc, p["description"])
    doc.add_heading("2. Cultural Background", level=1)
    para(doc, f"This piece belongs to the {p['craft'].lower()} tradition of {p['city']}, {p['region']}. "
              f"{CRAFT_NOTES.get(p['craft'], '')} It is made using {p['material'].lower()} through "
              f"{p['technique'].lower()}, a process associated with artisan communities of {p['region']}.")
    doc.add_heading("3. Dimensions", level=1)
    para(doc, "Exact dimensions are not recorded in the source catalogue for this item; treat as "
              "'not specified' rather than an assumed size.")
    doc.add_heading("4. Pricing", level=1)
    price_note = (
        "No competitor price has been verified for this academic/demo catalogue item."
        if p.get("competitor_price_inr") is None else
        "See documents/competitor/competitor_pricing.xlsx for an illustrative, academic-only reference "
        "price used for comparison exercises; it is not verified market data."
    )
    para(doc, f"The Kalakriti listing price is \u20b9{p['price_inr']:,}. {price_note}")
    doc.save(out_dir / f"{p['product_id']:02d}_{slug(p['name'])}.docx")


def make_products_catalog_xlsx(out_dir: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products"
    cols = ["Product ID", "Name", "Category", "Craft", "Region", "City", "Artisan", "Material",
            "Technique", "Price (INR)", "Rating", "Availability", "Image Path", "Product URL"]
    ws.append(cols)
    for p in CATALOG:
        ws.append([p["product_id"], p["name"], p["category"], p["craft"], p["region"], p["city"],
                   p["artisan"], p["material"], p["technique"], p["price_inr"], p["rating"],
                   p["availability"], p["image"], p["url"]])
    for col in ws.columns:
        letter = col[0].column_letter
        ws.column_dimensions[letter].width = max(12, min(38, max(len(str(c.value or "")) for c in col) + 2))
    wb.save(out_dir / "products_catalog.xlsx")


# --------------------------------------------------------------------------- competitor/*
def make_competitor_docs(out_dir: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Competitor Reference"
    ws.append(["Product ID", "Kalakriti Product", "Category", "Competitor (generic reference)",
               "Comparable Product", "Kalakriti Price (INR)", "Competitor Reference Price (INR)",
               "Difference (INR)", "Difference (%)", "Source / Reference", "Reference Period",
               "Comparability Notes"])
    for p in CATALOG:
        if p.get("competitor_price_inr") is None:
            continue
        ws.append([
            p["product_id"], p["name"], p["category"], "Illustrative Reference Marketplace",
            f"Comparable {p['category'].lower()} item", p["price_inr"], p["competitor_price_inr"],
            p["competitor_price_difference_inr"], p["competitor_price_difference_pct"],
            "Illustrative / Academic Demonstration Data - not a verified real-world quote",
            "Academic project reference (not time-stamped market data)",
            "Category-level illustrative multiplier; assumes a similar size/material tier, not a specific SKU.",
        ])
    for col in ws.columns:
        letter = col[0].column_letter
        ws.column_dimensions[letter].width = max(14, min(42, max(len(str(c.value or "")) for c in col) + 2))
    wb.save(out_dir / "competitor_pricing.xlsx")

    doc = docx.Document()
    title(doc, "Competitor Pricing Methodology")
    header_table(doc, [("Document Type", "Methodology Note"), ("Classification", "Internal - Academic Project"),
                        ("Data Status", "Illustrative / Academic Demonstration Data")])
    doc.add_heading("1. Purpose", level=1)
    para(doc, "This note documents how the competitor reference prices in competitor_pricing.xlsx were "
              "produced, so they are never mistaken for verified market research.")
    doc.add_heading("2. Method", level=1)
    para(doc, "Each product's reference price is the Kalakriti listing price multiplied by a fixed factor "
              "chosen per craft category (for example, Jewellery x1.40, Textile x1.28), rounded to the "
              "nearest ten rupees. The factors were set once for this academic project and were not fitted "
              "to, or sourced from, any real competitor's actual prices.")
    doc.add_heading("3. Explicit Disclaimer", level=1)
    para(doc, "These figures are ILLUSTRATIVE / ACADEMIC DEMONSTRATION DATA ONLY. They must not be presented, "
              "quoted, or relied upon as real market pricing, and the assistant is instructed to label them "
              "as such whenever it uses them in an answer.")
    doc.save(out_dir / "methodology_note.docx")


# --------------------------------------------------------------------------- regional/*.docx
def make_regional_docs(out_dir: Path) -> None:
    by_region = {r["region"]: r for r in HIERARCHY}
    products_by_region = defaultdict(list)
    for p in CATALOG:
        products_by_region[p["region"]].append(p)
    for region, info in by_region.items():
        doc = docx.Document()
        title(doc, f"{region} - Regional Craft Profile")
        header_table(doc, [("Document Type", "Regional Profile"), ("Region", region),
                            ("Cities Represented", ", ".join(c["city"] for c in info["cities"])),
                            ("Craft Categories", ", ".join(sorted({c for city in info["cities"] for c in city["crafts"]})))])
        doc.add_heading("1. Overview", level=1)
        para(doc, REGION_NOTES.get(region, f"{region} is represented in the Kalakriti catalogue."))
        doc.add_heading("2. Cities and Crafts", level=1)
        for city in info["cities"]:
            para(doc, f"{city['city']}: {', '.join(city['crafts'])} ({len(city['product_ids'])} catalogue item(s)).")
        doc.add_heading("3. Representative Products", level=1)
        for p in sorted(products_by_region[region], key=lambda x: x["product_id"])[:8]:
            para(doc, f"[{p['product_id']}] {p['name']} - {p['city']}, {p['craft']}, \u20b9{p['price_inr']:,} ({p['url']})")
        doc.save(out_dir / f"{slug(region)}.docx")


# --------------------------------------------------------------------------- craft/*.docx
def make_craft_docs(out_dir: Path) -> None:
    products_by_craft = defaultdict(list)
    regions_by_craft = defaultdict(set)
    for p in CATALOG:
        products_by_craft[p["craft"]].append(p)
        regions_by_craft[p["craft"]].add(p["region"])
    for craft, products in products_by_craft.items():
        doc = docx.Document()
        title(doc, f"{craft} - Craft Tradition")
        header_table(doc, [("Document Type", "Craft Profile"), ("Craft Category", craft),
                            ("Associated Regions", ", ".join(sorted(regions_by_craft[craft]))),
                            ("Catalogue Items", len(products))])
        doc.add_heading("1. About This Craft", level=1)
        para(doc, CRAFT_NOTES.get(craft, f"{craft} is one of the craft categories represented in the catalogue."))
        doc.add_heading("2. Materials and Techniques in the Catalogue", level=1)
        materials = sorted({p["material"] for p in products})
        techniques = sorted({p["technique"] for p in products})
        para(doc, "Materials: " + ", ".join(materials))
        para(doc, "Techniques: " + ", ".join(techniques))
        doc.add_heading("3. Representative Products", level=1)
        for p in sorted(products, key=lambda x: x["product_id"])[:8]:
            para(doc, f"[{p['product_id']}] {p['name']} - {p['city']}, {p['region']}, \u20b9{p['price_inr']:,} ({p['url']})")
        doc.save(out_dir / f"{slug(craft)}.docx")


# --------------------------------------------------------------------------- artisan/*
def make_artisan_doc(out_dir: Path) -> None:
    artisans: dict[str, dict] = {}
    for p in CATALOG:
        a = artisans.setdefault(p["artisan"], {
            "artisan": p["artisan"], "craft": p["craft"], "region": p["region"], "city": p["city"],
            "product_ids": [], "products": [],
        })
        a["product_ids"].append(p["product_id"])
        a["products"].append(p["name"])
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Artisans"
    ws.append(["Artisan ID", "Artisan / Collective", "Craft", "Region", "City", "Products", "Product Count"])
    for i, a in enumerate(sorted(artisans.values(), key=lambda x: x["artisan"]), start=1):
        ws.append([f"ART{i:03d}", a["artisan"], a["craft"], a["region"], a["city"],
                   "; ".join(a["products"]), len(a["products"])])
    for col in ws.columns:
        letter = col[0].column_letter
        ws.column_dimensions[letter].width = max(14, min(48, max(len(str(c.value or "")) for c in col) + 2))
    wb.save(out_dir / "artisans_directory.xlsx")
    print(f"  {len(artisans)} unique artisans")


def main() -> None:
    for sub in ("product", "competitor", "regional", "craft", "artisan"):
        (DOCS / sub).mkdir(parents=True, exist_ok=True)
    expected_product_docs = {f"{p['product_id']:02d}_{slug(p['name'])}.docx" for p in CATALOG}
    for stale in (DOCS / "product").glob("*.docx"):
        if stale.name not in expected_product_docs:
            stale.unlink()
    print("Generating product documents...")
    for p in CATALOG:
        make_product_doc(p, DOCS / "product")
    make_products_catalog_xlsx(DOCS / "product")
    print(f"  {len(CATALOG)} product DOCX + 1 catalogue XLSX")
    print("Generating competitor documents...")
    make_competitor_docs(DOCS / "competitor")
    print("Generating regional documents...")
    make_regional_docs(DOCS / "regional")
    print(f"  {len(HIERARCHY)} region DOCX")
    print("Generating craft documents...")
    make_craft_docs(DOCS / "craft")
    print("Generating artisan directory...")
    make_artisan_doc(DOCS / "artisan")
    print("Done.")


if __name__ == "__main__":
    main()
