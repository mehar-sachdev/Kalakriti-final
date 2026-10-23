"""Scoring functions for the Kalakriti RAG evaluation harness.

Every function here is pure and stdlib-only, so it can be unit tested without
a live Supabase/Ollama connection (see tests/test_evaluation_metrics.py). The
only thing these metrics know about is the shape of `SourceRef`-like dicts
returned by the engine (doc_code / document / department_slug) and plain
strings/numbers extracted from engine responses.
"""
from __future__ import annotations

import math
import re
from statistics import mean
from typing import Any, Iterable, Optional

_REFUSAL_PHRASES = (
    "do not provide sufficient information",
    "does not provide sufficient information",
    "not available in the current kalakriti knowledge base",
    "not available in the supplied",
    "is not available in",
    "no relevant documents were retrieved",
    "cannot find this in the available documents",
    "the available documents do not",
    "i don't have information",
    "i do not have information",
    "no information about this",
)

_CITE_RE = re.compile(r"\[(\d{1,2})\]")
_BRACKET_CITE_RE = re.compile(r"\[\d{1,2}\]")
_NUM_RE = re.compile(r"\d[\d,]*")


def retrieval_metrics(sources: list[dict], expected: dict, k: int) -> dict:
    """Hit / reciprocal-rank / precision / doc-recall for one question.

    `sources` is the ordered (by rank) list of retrieved source dicts, each
    with at least `doc_code`, `document` and `department_slug`. `expected`
    may give either `doc_codes` (exact match against `doc_code`) or
    `filenames` (case-insensitive match against the basename of `document`).
    An empty `expected` means retrieval correctness was not specified for
    this question, so `hit`/`rr`/`doc_recall` come back as `None` (not 0.0 -
    we were never told what "correct" looks like).
    """
    doc_codes = expected.get("doc_codes")
    filenames = expected.get("filenames")
    if not doc_codes and not filenames:
        return {"hit": None, "rr": None, "precision": None, "doc_recall": None}

    ranked = sources[:k]

    def _matches(src: dict) -> bool:
        if doc_codes and src.get("doc_code") in doc_codes:
            return True
        if filenames:
            basename = str(src.get("document", "")).rsplit("/", 1)[-1].lower()
            if basename in {f.lower() for f in filenames}:
                return True
        return False

    match_flags = [_matches(s) for s in ranked]
    hit = 1.0 if any(match_flags) else 0.0

    rr = 0.0
    for i, m in enumerate(match_flags):
        if m:
            rr = 1.0 / (i + 1)
            break

    precision = (sum(1 for m in match_flags if m) / k) if k else 0.0

    expected_count = len(doc_codes) if doc_codes else len(filenames or [])
    matched_targets: set[str] = set()
    for s in ranked:
        if doc_codes and s.get("doc_code") in doc_codes:
            matched_targets.add(s["doc_code"])
        if filenames:
            basename = str(s.get("document", "")).rsplit("/", 1)[-1].lower()
            for f in filenames:
                if basename == f.lower():
                    matched_targets.add(f.lower())
    doc_recall = (len(matched_targets) / expected_count) if expected_count else None

    return {"hit": hit, "rr": rr, "precision": precision, "doc_recall": doc_recall}


def department_isolation(sources: list[dict], department: Optional[str]) -> Optional[bool]:
    """True if every retrieved source stayed inside `department` (a region/craft
    slug in this project). None when there is nothing to check (no sources, or
    no department scoping was requested for this question)."""
    if not sources or department is None:
        return None
    return all(s.get("department_slug") == department for s in sources)


def contains_all_groups(text: str, groups: list[list[str]]) -> tuple[Optional[float], list[list[str]]]:
    """Fraction of fact-groups present in `text`, where a group is satisfied if
    ANY of its alternative spellings appears. `missing` lists the unsatisfied
    groups so a report can say exactly what was absent."""
    if not groups:
        return None, []
    missing: list[list[str]] = []
    hit_count = 0
    for group in groups:
        if any(alt in text for alt in group):
            hit_count += 1
        else:
            missing.append(group)
    return hit_count / len(groups), missing


def is_refusal(answer: str, has_sources: bool) -> bool:
    """Whether `answer` should be scored as a refusal/"I don't know" response.

    If nothing was retrieved (`has_sources=False`) there is no basis for a
    grounded answer, so any response is treated as an (expected) refusal
    regardless of wording. If sources were retrieved, we check the answer
    text itself for known refusal language - a model can still decline to
    answer even with context in hand (e.g. the context didn't cover it).
    """
    if not has_sources:
        return True
    lowered = answer.lower()
    return any(phrase in lowered for phrase in _REFUSAL_PHRASES)


def citation_validity(answer: str, valid_ids: Iterable[int]) -> dict:
    """Did the answer cite anything, and were the citations it used real?"""
    valid = set(valid_ids)
    cited = [int(m) for m in _CITE_RE.findall(answer)]
    has_citation = 1.0 if cited else 0.0
    if not cited:
        return {"has_citation": has_citation, "valid_citation_rate": None}
    valid_count = sum(1 for c in cited if c in valid)
    return {"has_citation": has_citation, "valid_citation_rate": valid_count / len(cited)}


def numeric_grounding(answer: str, context: list[str]) -> dict:
    """Checks every number quoted in the answer (ignoring citation markers like
    `[1]`) actually appears somewhere in the retrieved context, to catch the
    model inventing a figure that merely "sounds" plausible."""
    cleaned = _BRACKET_CITE_RE.sub("", answer)
    nums = [n.replace(",", "") for n in _NUM_RE.findall(cleaned)]
    if not nums:
        return {"rate": None, "ungrounded": []}
    ctx_text = " ".join(context)
    ctx_nums = {n.replace(",", "") for n in _NUM_RE.findall(ctx_text)}
    ungrounded = [n for n in nums if n not in ctx_nums]
    grounded = len(nums) - len(ungrounded)
    return {"rate": grounded / len(nums), "ungrounded": ungrounded}


def percentile(values: list[float], p: float) -> Optional[float]:
    """Nearest-rank percentile; None for an empty sample rather than raising."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    idx = max(0, min(n - 1, math.ceil(p / 100 * n) - 1))
    return s[idx]


def aggregate(results: list[dict]) -> dict:
    """Roll individual per-question metric dicts up into a report summary."""
    total = len(results)
    errors = sum(1 for r in results if "error" in r)
    valid = [r for r in results if "error" not in r]

    def _collect(key: str) -> list[float]:
        return [r[key] for r in valid if r.get(key) is not None]

    hits = _collect("hit")
    rrs = _collect("rr")
    precisions = _collect("precision")
    retrieved_counts = _collect("retrieved_count")
    fact_recalls = _collect("fact_recall")
    latencies = _collect("total_ms")

    refusal_expected = [r for r in valid if r.get("should_refuse") is True]
    out_of_scope_refused = (
        sum(1 for r in refusal_expected if r.get("refused")) / len(refusal_expected)
        if refusal_expected else None
    )

    return {
        "questions": total,
        "errors": errors,
        "retrieval": {
            "hit_rate": mean(hits) if hits else None,
            "mrr": mean(rrs) if rrs else None,
            "precision_mean": mean(precisions) if precisions else None,
            "retrieved_count_mean": mean(retrieved_counts) if retrieved_counts else None,
        },
        "answer": {
            "fact_recall_mean": mean(fact_recalls) if fact_recalls else None,
            "out_of_scope_refused": out_of_scope_refused,
        },
        "latency_ms": {
            "mean": mean(latencies) if latencies else None,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
        },
    }
