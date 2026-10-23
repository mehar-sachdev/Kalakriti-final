"""General (not hardcoded-per-example) typo tolerance for the chatbot.

Builds a vocabulary of every distinctive word that actually appears in the live product
catalogue (names, regions, cities, crafts, materials, techniques, artisans) plus the region/
city/craft hierarchy, then fuzzy-matches each word of the incoming question against it with
RapidFuzz. A word is only ever "corrected" when:
  - it is long enough to be meaningful (not "a", "is", "of" ...),
  - it is not already a real word used elsewhere in everyday English/retail phrasing
    (see `_COMMON_WORDS`) or already an exact vocabulary word,
  - it is not simply the regular English plural of an already-valid word
    (so "textiles" is never "corrected" to "Textile"),
  - and the closest vocabulary word is close enough (RapidFuzz ratio >= `_MATCH_THRESHOLD`).

This never special-cases the four example typos from the brief - it only knows the catalogue's
own vocabulary, so it generalises to any future catalogue item automatically.
"""
from __future__ import annotations

import re
from functools import lru_cache

from rapidfuzz import fuzz, process

from backend.rag import products as product_catalog

_MIN_WORD_LEN = 4
# High enough that an ordinary English word a few letters away from a catalogue term (e.g.
# "boiling" vs. the pottery/basketry technique "coiling", ratio ~86) is left alone, while all
# four typo examples from the brief (~89-94) and similar realistic typos still correct.
_MATCH_THRESHOLD = 87

# Ordinary English/retail words that must NEVER be "corrected" into a catalogue term just
# because they happen to be short or vaguely similar to one.
_COMMON_WORDS = {
    "this", "that", "these", "those", "what", "which", "who", "whom", "whose", "when", "where",
    "why", "how", "tell", "show", "about", "please", "with", "from", "have", "does", "made",
    "material", "materials", "made", "price", "prices", "pricing", "cost", "costs", "cheap",
    "cheaper", "cheapest", "expensive", "pricier", "costlier", "dearer", "priciest", "compare",
    "comparison", "competitor", "competitors", "reference", "product", "products", "item",
    "items", "catalogue", "catalog", "craft", "crafts", "region", "regions", "city", "cities",
    "artisan", "artisans", "available", "availability", "stock", "view", "link", "under",
    "over", "below", "above", "less", "more", "than", "some", "any", "all", "list", "find",
    "search", "know", "want", "need", "like", "looking", "show", "give", "information",
    "details", "detail", "online", "market", "current", "today", "much", "many", "good",
    "best", "nice", "lovely", "beautiful", "unknown", "something", "anything", "weather",
    "capital", "country", "france", "tokyo", "india", "indian", "handmade", "handcrafted",
    "traditional", "heritage", "quality", "stock", "order", "orders", "delivery", "shipping",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+", str(text or ""))


@lru_cache(maxsize=1)
def _vocabulary() -> dict[str, str]:
    """word (lowercase) -> canonical spelling, built from the live catalogue + hierarchy, not
    a fixed list - a new product automatically contributes new correctable vocabulary."""
    vocab: dict[str, str] = {}

    def add(value: str) -> None:
        for word in _words(value):
            if len(word) < _MIN_WORD_LEN:
                continue
            key = word.lower()
            vocab.setdefault(key, word)

    for product in product_catalog.load_catalog():
        for field in ("name", "region", "city", "craft", "material", "technique", "artisan"):
            add(str(product.get(field, "")))

    for region_row in product_catalog.load_hierarchy():
        add(region_row.get("region", ""))
        for city_row in region_row.get("cities", []):
            add(city_row.get("city", ""))
            for craft in city_row.get("crafts", []):
                add(craft)

    return vocab


def reset_cache() -> None:
    _vocabulary.cache_clear()


def _is_simple_plural_of(a: str, b: str) -> bool:
    """True if `a` is just the ordinary English plural of `b` (or vice versa) - a signal to
    leave the word alone rather than "correct" a perfectly valid plural/singular pair."""
    return a == b + "s" or a == b + "es" or b == a + "s" or b == a + "es"


def _correct_word(word: str) -> tuple[str, bool]:
    lowered = word.lower()
    if len(word) < _MIN_WORD_LEN:
        return word, False
    if lowered in _COMMON_WORDS:
        return word, False
    vocab = _vocabulary()
    if lowered in vocab:
        return word, False  # already a real catalogue word - nothing to fix

    match = process.extractOne(lowered, vocab.keys(), scorer=fuzz.ratio, score_cutoff=_MATCH_THRESHOLD)
    if match is None:
        return word, False
    matched_key = match[0]
    if _is_simple_plural_of(lowered, matched_key):
        return word, False

    canonical = vocab[matched_key]
    if canonical.lower() == lowered:
        return word, False
    return canonical, True


def correct_query(question: str) -> tuple[str, list[tuple[str, str]]]:
    """Returns (possibly-corrected question, [(original_word, corrected_word), ...]).

    Only alphabetic tokens are considered; punctuation, numbers and currency symbols pass
    through untouched. Safe to call on every question - most will come back unchanged."""
    fixes: list[tuple[str, str]] = []

    def _replace(match: re.Match) -> str:
        original = match.group(0)
        corrected, changed = _correct_word(original)
        if changed:
            fixes.append((original, corrected))
            return corrected
        return original

    corrected_text = re.sub(r"[A-Za-z]+", _replace, question)
    return corrected_text, fixes
