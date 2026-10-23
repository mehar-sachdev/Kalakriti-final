"""Small fakes so the engine and API are tested without Postgres, models or network."""
from __future__ import annotations

from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.vector_stores.types import MetadataFilters

DEPTS = [
    {"slug": "finance", "name": "Finance", "document_count": 2, "chunk_count": 5},
    {"slug": "hr", "name": "HR", "document_count": 1, "chunk_count": 2},
    {"slug": "sales-and-customer", "name": "Sales & Customer", "document_count": 1, "chunk_count": 2},
    {"slug": "legal-and-compliance", "name": "Legal & Compliance", "document_count": 1, "chunk_count": 1},
]


def node(text, score, *, dept="finance", dept_name="Finance", code="KAL-FIN-POL-009", doc="09_Expense_Policy.docx", page=2,
         doc_type="Policy", version="1.1", status="Active", section="5.1 Travel", **extra):
    meta = {"document_id": f"{dept}__{doc}", "doc_code": code, "title": doc.rsplit(".", 1)[0], "department": dept_name,
            "department_slug": dept, "source_filename": doc, "source_path": f"{dept_name}/{doc}", "file_type": doc.rsplit(".", 1)[-1],
            "document_type": doc_type, "version": version, "status": status, "section_path": section, "chunk_index": 0}
    if page:
        meta["page_number"] = page
    meta.update(extra)
    return NodeWithScore(node=TextNode(text=text, metadata=meta, id_=f"{doc}-{score}"), score=score)


class FakeRetriever:
    def __init__(self, nodes, filters, top_k, log):
        self.nodes, self.filters, self.top_k = nodes, filters, top_k
        log.append({"filters": filters, "top_k": top_k})

    def retrieve(self, bundle):
        out = list(self.nodes)
        if isinstance(self.filters, MetadataFilters):
            for f in self.filters.filters:
                out = [n for n in out if n.node.metadata.get(f.key) == f.value]
        return sorted(out, key=lambda n: n.score, reverse=True)[: self.top_k]


class FakeIndex:
    def __init__(self, nodes):
        self.nodes, self.log = nodes, []

    def as_retriever(self, similarity_top_k=10, filters=None):
        return FakeRetriever(self.nodes, filters, similarity_top_k, self.log)


class FakeRegistry:
    def department_stats(self):
        return DEPTS

    def list_documents(self, department_slug=None):
        return [{"document_type": "Policy"}, {"document_type": "SOP"}, {"document_type": "Matrix"}]


class FakeLLM:
    def __init__(self, answer="Answer text [1]."):
        self.answer, self.calls = answer, []

    def generate(self, system, user):
        self.calls.append((system, user))
        return self.answer


class FakeConversationStore:
    """In-memory stand-in for backend.database.conversations.ConversationStore - same interface,
    no Postgres required, so engine tests can exercise conversation memory/follow-up resolution
    without a live database."""

    def __init__(self, *, fail: bool = False):
        self._sessions: dict[str, dict] = {}
        self._messages: dict[str, list[dict]] = {}
        self.fail = fail

    def _maybe_fail(self):
        if self.fail:
            raise RuntimeError("simulated conversation store failure")

    def ensure_session(self, session_id: str) -> None:
        self._maybe_fail()
        self._sessions.setdefault(session_id, {"last_product_ids": []})

    def add_message(self, session_id, role, content, *, product_ids=None, sources=None):
        self._maybe_fail()
        self.ensure_session(session_id)
        self._messages.setdefault(session_id, []).append({
            "role": role, "content": content, "product_ids": list(product_ids or []), "sources": sources,
        })
        if product_ids:
            self._sessions[session_id]["last_product_ids"] = list(product_ids)

    def recent_messages(self, session_id: str, limit: int = 10):
        self._maybe_fail()
        return list(self._messages.get(session_id, []))[-limit:]

    def last_product_ids(self, session_id: str):
        self._maybe_fail()
        return list(self._sessions.get(session_id, {}).get("last_product_ids", []))

    def session_exists(self, session_id: str) -> bool:
        self._maybe_fail()
        return session_id in self._sessions
