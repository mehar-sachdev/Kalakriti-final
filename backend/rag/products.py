"""Structured product catalog operations.

The assignment (and good sense) says numeric filtering and comparison ("under ₹3000",
"largest competitor price difference") must not be left to semantic vector search alone -
a chunk containing "₹2,600" is not reliably found by cosine similarity to "products under
₹3000". This module answers those questions by loading and computing over the *same*
structured data the RAG documents were generated from (data/metadata/products.json), so
the numbers are always exact and never hallucinated. The LLM is used only to phrase a
sentence around facts this module already computed - never to do the arithmetic itself.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "metadata" / "products.json"
_HIERARCHY_PATH = _CATALOG_PATH.parent / "region_city_craft.json"


@lru_cache(maxsize=1)
def load_catalog(path: Path | None = None) -> list[dict]:
    p = path or _CATALOG_PATH
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_hierarchy(path: Path | None = None) -> list[dict]:
    p = path or _HIERARCHY_PATH
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def reset_cache() -> None:
    load_catalog.cache_clear()
    load_hierarchy.cache_clear()


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def get_product(product_id: int) -> Optional[dict]:
    return next((p for p in load_catalog() if p["product_id"] == product_id), None)


_NAME_STOPWORDS = {"and", "of", "for", "the", "with", "a", "an"}


def slugify_product_name(name: str) -> str:
    """Match the generator's stable ASCII product-document filename convention."""
    import unicodedata

    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")


def find_by_name(query: str, limit: int = 5) -> list[dict]:
    """Match a product mentioned in natural phrasing, e.g. 'Tell me about the Chikankari
    Embroidered Kurta' -> that product. Checked as containment of the PRODUCT NAME's distinctive
    words in the query (not the reverse), since a question is full of words - "tell", "about",
    "show" - that will never appear in any product name."""
    q = _norm(query)
    hits = []
    for p in load_catalog():
        name_words = [w for w in _norm(p["name"]).split() if w not in _NAME_STOPWORDS]
        if name_words and all(w in q for w in name_words):
            hits.append(p)
    hits.sort(key=lambda p: len(p["name"]), reverse=True)  # more specific (longer) name matches first
    return hits[:limit]


def filter_products(
    *, region: str | None = None, city: str | None = None, craft: str | None = None,
    max_price: float | None = None, min_price: float | None = None, limit: int = 20,
) -> list[dict]:
    items = load_catalog()
    if region:
        want = _norm(region)
        items = [p for p in items if want in _norm(p["region"]) or _norm(p["region"]) in want]
    if city:
        want = _norm(city)
        items = [p for p in items if want in _norm(p["city"]) or _norm(p["city"]) in want]
    if craft:
        want = _norm(craft)
        items = [p for p in items if want in _norm(p["craft"]) or _norm(p["craft"]) in want]
    if max_price is not None:
        items = [p for p in items if p["price_inr"] <= max_price]
    if min_price is not None:
        items = [p for p in items if p["price_inr"] >= min_price]
    return items[:limit]


def cheaper_than_competitor(limit: int = 20) -> list[dict]:
    items = [p for p in load_catalog() if p.get("competitor_price_inr") is not None and p["price_inr"] < p["competitor_price_inr"]]
    return sorted(items, key=lambda p: p["competitor_price_difference_pct"], reverse=True)[:limit]


def largest_price_difference(limit: int = 5) -> list[dict]:
    items = [p for p in load_catalog() if p.get("competitor_price_difference_inr") is not None]
    items = sorted(items, key=lambda p: abs(p["competitor_price_difference_inr"]), reverse=True)
    return items[:limit]


def price_difference(product_id: int) -> Optional[dict]:
    p = get_product(product_id)
    if p is None or p.get("competitor_price_inr") is None:
        return None
    return {
        "product_id": p["product_id"], "name": p["name"], "kalakriti_price_inr": p["price_inr"],
        "competitor_reference_price_inr": p["competitor_price_inr"],
        "difference_inr": p["competitor_price_difference_inr"],
        "difference_pct": p["competitor_price_difference_pct"],
        "illustrative": True,
    }


# ---------------------------------------------------------------------------- lightweight intent detection
_PRICE_UNDER_RE = re.compile(r"under|below|less than|cheaper than|up to", re.I)
_PRICE_OVER_RE = re.compile(r"over|above|more than|greater than", re.I)
_AMOUNT_RE = re.compile(r"₹?\s?([\d,]{3,7})")
_COMPETITOR_RE = re.compile(r"competitor|market price|reference price|cheaper than (?:the )?(?:market|competitor)", re.I)
_LARGEST_DIFF_RE = re.compile(r"largest|biggest|highest (?:price )?difference|most expensive relative", re.I)
_PRODUCT_ID_RE = re.compile(r"product\s*(?:id|#)?\s*(\d{1,3})\b", re.I)


def detect_facets(question: str) -> dict[str, str]:
    """Find an explicit region/city/craft named in the question (exact-name matches only,
    longest name wins per facet so 'Jammu & Kashmir' beats a stray word match)."""
    q = " " + _norm(question) + " "
    facets: dict[str, str] = {}
    hierarchy = load_hierarchy()
    regions = sorted({r["region"] for r in hierarchy}, key=len, reverse=True)
    for region in regions:
        if f" {_norm(region)} " in q:
            facets["region"] = region
            break
    cities = sorted({c["city"] for r in hierarchy for c in r["cities"]}, key=len, reverse=True)
    for city in cities:
        if f" {_norm(city)} " in q:
            facets["city"] = city
            break
    crafts = sorted({p["craft"] for p in load_catalog()}, key=len, reverse=True)
    for craft in crafts:
        if f" {_norm(craft)} " in q:
            facets["craft"] = craft
            break
    if "craft" not in facets:
        # No exact craft-category name in the question ("weaving", "embroidery", "block printing" are
        # technique words, not category names) - infer from technique text actually present in the catalogue.
        words = [w for w in q.split() if len(w) > 3]
        matched_crafts = {
            p["craft"] for p in load_catalog() if any(w in _norm(p["technique"]) for w in words)
        }
        if len(matched_crafts) == 1:
            facets["craft"] = next(iter(matched_crafts))
    return facets


_LIVE_QUERY_STOPWORDS = _NAME_STOPWORDS | {
    "what", "is", "current", "competitor", "competitors", "price", "cost", "live",
    "compare", "comparison", "market", "online", "elsewhere", "how", "much", "for",
}


def find_best_partial_name(query: str) -> Optional[dict]:
    """Resolve a live-price query that names a product/category without its full title.

    City and craft facets narrow broad phrases first; at least two distinctive name tokens
    must then match. Ties prefer the shorter, more specific catalogue title, then stable ID.
    """
    query_words = {word for word in _norm(query).split() if word not in _LIVE_QUERY_STOPWORDS}
    if len(query_words) < 2:
        return None

    facets = detect_facets(query)
    candidates = load_catalog()
    if facets.get("region"):
        candidates = [p for p in candidates if p["region"] == facets["region"]]
    if facets.get("city"):
        candidates = [p for p in candidates if p["city"] == facets["city"]]
    if facets.get("craft"):
        candidates = [p for p in candidates if p["craft"] == facets["craft"]]

    ranked: list[tuple[int, int, int, dict]] = []
    for product in candidates:
        name_words = {word for word in _norm(product["name"]).split() if word not in _NAME_STOPWORDS}
        overlap = len(query_words & name_words)
        if overlap >= 2:
            ranked.append((-overlap, len(name_words), product["product_id"], product))
    ranked.sort(key=lambda result: result[:3])
    return ranked[0][3] if ranked else None


@dataclass
class Intent:
    kind: str                          # price_filter | competitor_cheaper | largest_diff | product_diff | none
    max_price: float | None = None
    min_price: float | None = None
    product_id: int | None = None


def detect_intent(question: str, matched_product_ids: list[int] | None = None) -> Intent:
    """Conservative, regex-based detection - only fires on explicit numeric/comparison language."""
    amounts = [int(a.replace(",", "")) for a in _AMOUNT_RE.findall(question)]
    pid_match = _PRODUCT_ID_RE.search(question)
    explicit_pid = int(pid_match.group(1)) if pid_match else None

    if _LARGEST_DIFF_RE.search(question) and _COMPETITOR_RE.search(question):
        return Intent("largest_diff")
    if _COMPETITOR_RE.search(question):
        pid = explicit_pid or (matched_product_ids[0] if matched_product_ids else None)
        if pid is not None:
            return Intent("product_diff", product_id=pid)
        return Intent("competitor_cheaper")
    if amounts and (_PRICE_UNDER_RE.search(question) or _PRICE_OVER_RE.search(question)):
        amount = amounts[0]
        if _PRICE_UNDER_RE.search(question):
            return Intent("price_filter", max_price=amount)
        return Intent("price_filter", min_price=amount)
    return Intent("none")
