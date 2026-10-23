"""Department-aware retrieval helpers: filter building, name resolution, post-processing."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.vector_stores.types import FilterOperator, MetadataFilter, MetadataFilters

from backend.exceptions import RAGError
from backend.ingestion.discovery import slugify

ALL_DEPARTMENTS = {"", "all", "all departments", "any", "*"}


class UnknownDepartment(RAGError):
    code = "unknown_department"
    http_status = 422


@dataclass(frozen=True)
class Dept:
    slug: str
    name: str


# ---------------------------------------------------------------------------- name resolution
def resolve_department(value: Optional[str], departments: list[Dept]) -> Optional[str]:
    """Map user input ('finance', 'Legal', 'Sales & Customer') to a department slug.

    Returns None for 'all'.  Accepts exact name/slug or a unique word of the name
    ('legal' -> 'legal-and-compliance').  Raises UnknownDepartment otherwise.
    """
    if value is None or value.strip().lower() in ALL_DEPARTMENTS:
        return None
    wanted = slugify(value)
    for d in departments:
        if wanted == d.slug or value.strip().lower() == d.name.lower():
            return d.slug
    partial = [d for d in departments if wanted in d.slug.split("-") or d.slug.startswith(wanted + "-")]
    if len(partial) == 1:
        return partial[0].slug
    known = ", ".join(sorted(d.name for d in departments)) or "none indexed yet"
    if len(partial) > 1:
        raise UnknownDepartment(f"Department '{value}' is ambiguous.", hint=f"Use one of: {known}.")
    raise UnknownDepartment(f"Unknown department '{value}'.", hint=f"Available departments: {known}.")


_STOP_TOKENS = {"and", "the", "of", "customer", "service", "services", "operations", "product"}


def _aliases(dept: Dept) -> set[str]:
    aliases = {dept.name.lower(), dept.slug.replace("-", " ")}
    first = re.split(r"\s*(?:&|/|,| and )\s*", dept.name, maxsplit=1)[0].strip().lower()
    if first:
        aliases.add(first)
    return {a for a in aliases if a and a not in _STOP_TOKENS}


def infer_department(question: str, departments: list[Dept]) -> Optional[Dept]:
    """Conservative detection of phrases such as "the Finance department's reimbursement policy".

    Only explicit forms count (X department/dept/team, department of X, X's <thing>, from/in the X
    documents).  Ambiguous or multiple matches return None so no wrong filter is applied silently.
    """
    q = question.lower()
    hits: dict[str, Dept] = {}
    for dept in departments:
        for alias in _aliases(dept):
            a = re.escape(alias)
            patterns = [
                rf"\b{a}(?:'s|’s)?\s+(?:department|dept|team)\b",
                rf"\b(?:department|dept|team)\s+of\s+{a}\b",
                rf"\b{a}(?:'s|’s)\s+\w+",
                rf"\b(?:from|in|within)\s+(?:the\s+)?{a}\s+(?:documents?|docs?|files?|folder|policies|policy)\b",
            ]
            if any(re.search(p, q) for p in patterns):
                hits[dept.slug] = dept
    return next(iter(hits.values())) if len(hits) == 1 else None


# ---------------------------------------------------------------------------- filters
def build_metadata_filters(
    department_slug: Optional[str] = None, document_type: Optional[str] = None, filename: Optional[str] = None
) -> Optional[MetadataFilters]:
    filters = []
    if department_slug:
        filters.append(MetadataFilter(key="department_slug", value=department_slug, operator=FilterOperator.EQ))
    if document_type:
        filters.append(MetadataFilter(key="document_type", value=document_type, operator=FilterOperator.EQ))
    if filename:
        filters.append(MetadataFilter(key="source_filename", value=filename, operator=FilterOperator.EQ))
    return MetadataFilters(filters=filters) if filters else None


# ---------------------------------------------------------------------------- post-processors
def _shingles(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


class DedupPostprocessor(BaseNodePostprocessor):
    """Drops near-duplicate chunks (e.g. an Excel matrix that restates its source policy).

    Two chunks with token-set Jaccard >= ``threshold`` are duplicates; the higher-scored one is kept.
    """

    threshold: float = 0.9

    @classmethod
    def class_name(cls) -> str:
        return "DedupPostprocessor"

    def _postprocess_nodes(self, nodes: list[NodeWithScore], query_bundle: Optional[QueryBundle] = None) -> list[NodeWithScore]:
        kept: list[tuple[NodeWithScore, set[str]]] = []
        for item in sorted(nodes, key=lambda n: n.score or 0.0, reverse=True):
            tokens = _shingles(item.node.get_content())
            duplicate = False
            for _, other in kept:
                union = tokens | other
                if union and len(tokens & other) / len(union) >= self.threshold:
                    duplicate = True
                    break
            if not duplicate:
                kept.append((item, tokens))
        return [item for item, _ in kept]


def relevance_filter(nodes: list[NodeWithScore], cutoff: float) -> list[NodeWithScore]:
    return [n for n in nodes if (n.score or 0.0) >= cutoff]
