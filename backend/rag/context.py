"""Resolves follow-up questions ("What is its price?", "Which one is cheaper?", "Tell me more
about it.") against the products actually discussed in recent turns of THIS conversation.

Deliberately not a second LLM call: it is a small, explainable rewrite step that runs before
retrieval. It replaces the pronoun/referent with the real product name, so every existing
piece of downstream logic (find_by_name, detect_intent, the product card layer) keeps working
completely unchanged - they simply see a question that already names the product.

Conservative by design: if there is real ambiguity (three or more products were on the table
and the user just said "it"), this does NOT guess - it leaves the question untouched and lets
the normal "which product did you mean" behaviour take over, rather than silently picking the
wrong one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from backend.rag import products as product_catalog

_REFERENT_RE = re.compile(
    r"\b(it|this product|this one|this item|that product|that one|that item|the product|its|it's)\b",
    re.I,
)
_SUPERLATIVE_CHEAPER_RE = re.compile(
    r"\b(which|the)\s+(one|product)?\s*(is\s+)?(cheap(?:er|est)|less expensive|more affordable)\b", re.I,
)
_SUPERLATIVE_PRICIER_RE = re.compile(
    r"\b(which|the)\s+(one|product)?\s*(is\s+)?(more expensive|pricier|costlier|dearer|priciest|most expensive)\b",
    re.I,
)


@dataclass
class ResolvedFollowUp:
    question: str
    rewritten: bool = False
    resolved_product_id: Optional[int] = None


def _dedup(ids: list[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for pid in ids:
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def has_referent(question: str) -> bool:
    return bool(_REFERENT_RE.search(question))


def _substitute_referent(question: str, product: dict) -> str:
    name = product["name"]

    def _sub(match: re.Match) -> str:
        word = match.group(0).lower()
        if word in ("its", "it's"):
            return f"{name}'s"
        return name

    return _REFERENT_RE.sub(_sub, question)


def resolve_followup(question: str, history_product_ids: list[int]) -> ResolvedFollowUp:
    """`history_product_ids` should be the product ids discussed in recent turns, most-recently-
    discussed first (duplicates are fine - deduped here)."""
    candidates = _dedup([pid for pid in history_product_ids if pid is not None])
    if not candidates:
        return ResolvedFollowUp(question=question, rewritten=False)

    superlative_match = _SUPERLATIVE_CHEAPER_RE.search(question) or _SUPERLATIVE_PRICIER_RE.search(question)
    wants_cheaper = bool(_SUPERLATIVE_CHEAPER_RE.search(question))

    if superlative_match:
        products = [p for p in (product_catalog.get_product(pid) for pid in candidates) if p]
        if len(products) >= 2:
            chosen = min(products, key=lambda p: p["price_inr"]) if wants_cheaper else max(products, key=lambda p: p["price_inr"])
            # Deliberately do NOT spell out the other candidates' full names here: find_by_name()
            # downstream matches on name-word containment, and listing every other product's name
            # would make it match ALL of them again, undoing the single-product resolution we just
            # did. Naming only the chosen product keeps the rewrite unambiguous for every later step.
            comparison_label = "cheaper" if wants_cheaper else "more expensive"
            replacement = (
                f"{chosen['name']} (₹{chosen['price_inr']:,.0f}), the {comparison_label} "
                f"of the {len(products)} options shown"
            )
            rewritten_text = question[:superlative_match.start()] + replacement + question[superlative_match.end():]
            return ResolvedFollowUp(question=rewritten_text, rewritten=True, resolved_product_id=chosen["product_id"])
        # Only one (or zero) candidate products actually resolved - nothing to compare, fall
        # through to plain-referent handling below (there may still be an "it" elsewhere).

    if has_referent(question):
        if len(candidates) == 1:
            product = product_catalog.get_product(candidates[0])
            if product is None:
                return ResolvedFollowUp(question=question, rewritten=False)
            rewritten_text = _substitute_referent(question, product)
            return ResolvedFollowUp(question=rewritten_text, rewritten=True, resolved_product_id=product["product_id"])
        # 2+ candidates and just a bare pronoun: genuinely ambiguous, do not guess.
        return ResolvedFollowUp(question=question, rewritten=False)

    return ResolvedFollowUp(question=question, rewritten=False)
