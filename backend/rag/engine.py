"""Query pipeline: filters -> vector retrieval -> post-processing -> grounded generation -> citations.

    question
       |  (department / type / file filters, optional department detection)
       v
    embed query -> pgvector HNSW search (metadata-filtered)
       v
    similarity cut-off -> de-duplication -> (optional cross-encoder rerank) -> top-k
       v
    numbered context  -> Ollama Cloud LLM (system prompt forbids inventing facts)
       v
    answer with [n] markers  +  structured sources (document, department, page/sheet/section, score)

If nothing relevant is retrieved, the LLM is *not* called: the answer is the fixed
"insufficient information" message - cheaper, faster and impossible to hallucinate.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from llama_index.core import Settings as LlamaSettings
from llama_index.core import VectorStoreIndex
from llama_index.core.schema import NodeWithScore, QueryBundle

from backend.config import Settings
from backend.database.connection import explain_db_error, get_engine
from backend.database.conversations import ConversationStore
from backend.database.registry import DocumentRegistry
from backend.database.vector_store import build_vector_store
from backend.exceptions import DatabaseError, EmbeddingError, OffPeakRestricted, RAGError
from backend.logging_config import redact
from backend.models.schemas import LivePriceStatus, ProductCard, QueryRequest, QueryResponse, Timings
from backend.rag import products as product_catalog
from backend.rag.citations import extract_cited_ids, node_to_source
from backend.rag.context import resolve_followup
from backend.rag.embeddings import get_embed_model
from backend.rag.llm import LLMGateway
from backend.rag.prompts import (
    INSUFFICIENT_INFO_ANSWER,
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    build_context,
    render_conversation_history,
    render_structured_facts,
)
from backend.rag.retrieval import (
    DedupPostprocessor,
    Dept,
    build_metadata_filters,
    infer_department,
    relevance_filter,
    resolve_department,
)
from backend.rag.spelling import correct_query
from backend.rag.web_prices import is_live_competitor_question, retrieve_live_competitor_price

logger = logging.getLogger(__name__)
_INSUFFICIENT_MARKERS = ("could not find this information", "do not provide sufficient information", "does not provide sufficient information")
_PRODUCT_LIST_RE = re.compile(r"\bproducts\b|\bitems\b|\bones\b", re.I)


class RAGEngine:
    def __init__(
        self,
        settings: Settings,
        *,
        embed_model=None,
        vector_store=None,
        registry: DocumentRegistry | None = None,
        llm_gateway: LLMGateway | None = None,
        conversations: ConversationStore | None = None,
    ):
        self.settings = settings
        self._embed_model = embed_model
        self._vector_store = vector_store
        self._registry = registry
        self._conversations = conversations
        self._index: VectorStoreIndex | None = None
        self.llm = llm_gateway or LLMGateway(settings)
        self._reranker = None
        self._dept_cache: tuple[float, list[Dept]] | None = None
        self._type_cache: tuple[float, dict[str, str]] | None = None

    # ------------------------------------------------------------------ lazy components
    @property
    def embed_model(self):
        if self._embed_model is None:
            self._embed_model = get_embed_model(self.settings)
        return self._embed_model

    @property
    def registry(self) -> DocumentRegistry:
        if self._registry is None:
            self._registry = DocumentRegistry(get_engine(self.settings), self.settings)
        return self._registry

    @property
    def conversations(self) -> ConversationStore | None:
        """None when Supabase isn't configured - conversation memory degrades gracefully to
        "no history available" rather than making the whole chat depend on it."""
        if self._conversations is None and self.settings.supabase_db_url is not None:
            self._conversations = ConversationStore(get_engine(self.settings), self.settings)
        return self._conversations

    def _load_conversation(self, request: QueryRequest) -> tuple[Optional[str], list[int], list[dict]]:
        """Returns (session_id, recent product ids most-recent-first, recent messages). A
        problem talking to the database must never break the chat - any error just means "no
        history available this turn", logged and swallowed, same as the live-price lookup."""
        session_id = request.session_id or uuid.uuid4().hex
        if self.conversations is None:
            return session_id, [], []
        try:
            if not request.session_id:
                return session_id, [], []
            recent = self.conversations.recent_messages(session_id, limit=10)
            # Only the MOST RECENT turn's products count as "what we're discussing now" - not
            # everything ever mentioned in the conversation. This is what lets scenario D work:
            # turn 1 shows 8 Rajasthan products (too ambiguous for a bare "it"), turn 2 narrows
            # that down to the one cheapest product, and turn 3's "tell me more about it" must
            # resolve against THAT one product, not fall back into the original ambiguous set of 8.
            history_product_ids = list(self.conversations.last_product_ids(session_id))
            return session_id, history_product_ids, recent
        except Exception as exc:  # noqa: BLE001 - never let a DB hiccup break the chat
            logger.warning("Could not load conversation history (%s); continuing without it.", type(exc).__name__)
            return session_id, [], []

    def _store_turn(
        self, session_id: Optional[str], raw_question: str, answer: str,
        product_cards: list[ProductCard], sources: list,
    ) -> None:
        if not session_id or self.conversations is None:
            return
        try:
            self.conversations.add_message(session_id, "user", raw_question)
            self.conversations.add_message(
                session_id, "assistant", answer,
                product_ids=[c.product_id for c in product_cards],
                sources=[s.document for s in sources] if sources else None,
            )
        except Exception as exc:  # noqa: BLE001 - never let a DB hiccup break the chat
            logger.warning("Could not store this conversation turn (%s); the answer is unaffected.", type(exc).__name__)

    @property
    def index(self) -> VectorStoreIndex:
        if self._index is None:
            if self._vector_store is None:
                self._vector_store = build_vector_store(self.settings)
            LlamaSettings.llm = None  # retrieval only; generation goes through LLMGateway
            LlamaSettings.embed_model = self.embed_model
            self._index = VectorStoreIndex.from_vector_store(self._vector_store, embed_model=self.embed_model)
        return self._index

    def _departments(self) -> list[Dept]:
        now = time.monotonic()
        if self._dept_cache and now - self._dept_cache[0] < 60:
            return self._dept_cache[1]
        rows = self.registry.department_stats()
        depts = [Dept(r["slug"], r["name"]) for r in rows]
        self._dept_cache = (now, depts)
        return depts

    def _document_types(self) -> dict[str, str]:
        now = time.monotonic()
        if self._type_cache and now - self._type_cache[0] < 60:
            return self._type_cache[1]
        types = {(r.get("document_type") or "").lower(): r["document_type"] for r in self.registry.list_documents() if r.get("document_type")}
        self._type_cache = (now, types)
        return types

    # ------------------------------------------------------------------ retrieval
    def retrieve(
        self, question: str, *, department_slug: Optional[str] = None, document_type: Optional[str] = None,
        filename: Optional[str] = None, top_k: Optional[int] = None,
    ) -> list[NodeWithScore]:
        k = top_k or self.settings.top_k
        candidates = max(k, self.settings.rerank_candidates) if self.settings.rerank_enabled else max(k * 2, k + 4)
        filters = build_metadata_filters(department_slug, document_type, filename)
        retriever = self.index.as_retriever(similarity_top_k=candidates, filters=filters)
        bundle = QueryBundle(query_str=question)
        try:
            nodes = retriever.retrieve(bundle)
        except RAGError:
            raise
        except Exception as exc:  # noqa: BLE001
            text = f"{type(exc).__name__}: {exc}"
            if "embed" in text.lower() or "SentenceTransformer" in text or "Ollama" in text and "embed" in text.lower():
                raise EmbeddingError(redact(text)[:300], hint="Check the embedding model configuration.") from exc
            raise explain_db_error(exc) from exc

        nodes = relevance_filter(nodes, self.settings.similarity_cutoff)
        nodes = DedupPostprocessor().postprocess_nodes(nodes, bundle)
        if self.settings.rerank_enabled and nodes:
            nodes = self._rerank(nodes, bundle, k)
        return sorted(nodes, key=lambda n: n.score or 0.0, reverse=True)[:k]

    def _rerank(self, nodes: list[NodeWithScore], bundle: QueryBundle, top_n: int) -> list[NodeWithScore]:
        if self._reranker is None:
            try:
                from llama_index.core.postprocessor import SentenceTransformerRerank

                self._reranker = SentenceTransformerRerank(model=self.settings.rerank_model, top_n=top_n)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reranker unavailable (%s); continuing without it.", redact(str(exc))[:120])
                self.settings.__dict__["rerank_enabled"] = False
                return nodes
        self._reranker.top_n = top_n
        return self._reranker.postprocess_nodes(nodes, bundle)

    # ------------------------------------------------------------------ product-aware layer
    @staticmethod
    def _to_card(p: dict) -> ProductCard:
        return ProductCard(
            product_id=p["product_id"], name=p["name"], category=p["category"], region=p["region"],
            city=p["city"], price_inr=p["price_inr"], competitor_price_inr=p.get("competitor_price_inr"),
            competitor_price_is_illustrative=p.get("competitor_price_is_illustrative"),
            image=p["image"], url=p["url"],
        )

    def _product_layer(self, question: str) -> tuple[list[ProductCard], str | None]:
        """Answer numeric/comparison questions from structured product data rather than hoping
        vector search finds the right number. Returns (product cards for the response, a
        computed-facts block to hand the LLM instead of/alongside retrieved excerpts)."""
        matched = product_catalog.find_by_name(question)
        matched_ids = [p["product_id"] for p in matched]
        intent = product_catalog.detect_intent(question, matched_ids)
        facets = product_catalog.detect_facets(question)
        to_card = self._to_card

        if intent.kind == "price_filter":
            items = product_catalog.filter_products(
                region=facets.get("region"), city=facets.get("city"), craft=facets.get("craft"),
                max_price=intent.max_price, min_price=intent.min_price, limit=8,
            )
            label = f"products under ₹{intent.max_price:,.0f}" if intent.max_price else f"products over ₹{intent.min_price:,.0f}"
            if not items:
                return [], f"[Computed facts - {label}] No catalogue product matches this filter."
            facts = [{"product": p["name"], "price_inr": p["price_inr"], "region": p["region"], "city": p["city"]} for p in items]
            return [to_card(p) for p in items], render_structured_facts(label, facts)

        if intent.kind == "competitor_cheaper":
            items = product_catalog.cheaper_than_competitor(limit=8)
            facts = [{"product": p["name"], "kalakriti_price_inr": p["price_inr"],
                      "illustrative_competitor_reference_price_inr": p["competitor_price_inr"],
                      "difference_inr": p["competitor_price_difference_inr"]} for p in items]
            return [to_card(p) for p in items], render_structured_facts(
                "cheaper than the illustrative competitor reference price", facts)

        if intent.kind == "largest_diff":
            items = product_catalog.largest_price_difference(limit=5)
            facts = [{"product": p["name"], "kalakriti_price_inr": p["price_inr"],
                      "illustrative_competitor_reference_price_inr": p["competitor_price_inr"],
                      "difference_inr": p["competitor_price_difference_inr"],
                      "difference_pct": p["competitor_price_difference_pct"]} for p in items]
            return [to_card(p) for p in items], render_structured_facts(
                "largest illustrative competitor price difference", facts)

        if intent.kind == "product_diff" and intent.product_id is not None:
            diff = product_catalog.price_difference(intent.product_id)
            p = product_catalog.get_product(intent.product_id)
            if diff is None or p is None:
                return [], None
            return [to_card(p)], render_structured_facts(f"price comparison for {p['name']}", [diff])

        if matched:
            cards = [to_card(p) for p in matched[:5]]
            facts = [{"product": p["name"], "price_inr": p["price_inr"], "region": p["region"], "city": p["city"]} for p in matched[:5]]
            return cards, render_structured_facts("matched products", facts)

        if facets:
            items = product_catalog.filter_products(
                region=facets.get("region"), city=facets.get("city"), craft=facets.get("craft"), limit=8
            )
            if not items:
                return [], None
            facts = [{"product": p["name"], "price_inr": p["price_inr"], "region": p["region"], "city": p["city"]} for p in items]
            label = " / ".join(f"{k}: {v}" for k, v in facets.items())
            return [to_card(p) for p in items], render_structured_facts(f"products matching {label}", facts)

        return [], None

    # ------------------------------------------------------------------ full query
    def query(self, request: QueryRequest, *, excerpt_chars: int | None = 420) -> QueryResponse:
        """Answer a question. ``excerpt_chars=None`` returns full chunk text (used by the evaluation)."""
        started = time.perf_counter()
        settings = self.settings
        off_peak = settings.is_off_peak()
        notice = None
        if settings.offpeak_enabled and not off_peak:
            window = f"{settings.offpeak_start}-{settings.offpeak_end} {settings.offpeak_tz}"
            if settings.offpeak_enforce:
                raise OffPeakRestricted(
                    "The assistant only answers during the configured off-peak window.",
                    hint=f"Try again between {window}. (Set OFFPEAK_ENFORCE=false to allow peak-time use.)",
                )
            notice = f"Outside the off-peak window ({window}); Ollama Cloud may be slower or rate-limited."

        # --- conversation memory: load history, then typo-correct + resolve follow-ups -------
        raw_question = request.question
        session_id, history_product_ids, recent_messages = self._load_conversation(request)

        corrected_question, spelling_fixes = correct_query(raw_question)
        effective_question = corrected_question
        if spelling_fixes:
            logger.info("Typo-corrected query: %r -> %r (%s)", raw_question, corrected_question, spelling_fixes)

        already_names_a_product = bool(product_catalog.find_by_name(effective_question))
        if history_product_ids and not already_names_a_product:
            resolved = resolve_followup(effective_question, history_product_ids)
            if resolved.rewritten:
                logger.info("Follow-up resolved: %r -> %r", effective_question, resolved.question)
                effective_question = resolved.question

        if effective_question != request.question:
            request = request.model_copy(update={"question": effective_question})

        applied: dict[str, object] = {}
        departments = self._departments()
        department_slug = resolve_department(request.department, departments)
        if department_slug:
            applied["department"] = department_slug
        elif settings.auto_department_detection and request.department is None:  # explicit "all" = search everything
            inferred = infer_department(request.question, departments)
            if inferred:
                department_slug = inferred.slug
                applied.update({"department": inferred.slug, "department_inferred": True})

        document_type = None
        if request.document_type:
            document_type = self._document_types().get(request.document_type.lower(), request.document_type)
            applied["document_type"] = document_type
        if request.filename:
            applied["filename"] = request.filename

        # A question like "Which products are cheaper than the competitor?" or "Which product has
        # the largest competitor price difference?" names no single product on purpose - it wants
        # the structured multi-product answer from the catalogue, not a live single-product web
        # lookup (and must not be told to "name one catalogue product"). Only a genuinely
        # single-product live-price question (e.g. "Is this cheaper than the competitor?",
        # "What is the current competitor price?") should go through the live-web-search path.
        _matched_for_intent = product_catalog.find_by_name(request.question)
        _intent = product_catalog.detect_intent(request.question, [p["product_id"] for p in _matched_for_intent])
        wants_product_list = _intent.kind == "largest_diff" or (
            _intent.kind == "competitor_cheaper" and _PRODUCT_LIST_RE.search(request.question)
        )

        live_price_request = is_live_competitor_question(request.question) and not wants_product_list
        live_product_matches = product_catalog.find_by_name(request.question) if live_price_request else []
        live_product = (
            live_product_matches[0] if len(live_product_matches) == 1 else
            product_catalog.find_best_partial_name(request.question) if live_price_request and not live_product_matches else
            None
        )
        if live_price_request and live_product is None:
            self._store_turn(
                session_id, raw_question,
                "Please name one Kalakriti catalogue product so I can search for a comparable current price.",
                [], [],
            )
            return QueryResponse(
                answer="Please name one Kalakriti catalogue product so I can search for a comparable current price.",
                products=[], sources=[], grounded=False, retrieved_count=0, applied_filters=applied, model=None,
                live_price_status=LivePriceStatus(
                    verified=False, message="No current competitor price was verified: no single catalogue product was named.",
                ),
                timings=Timings(total_ms=int((time.perf_counter() - started) * 1000)),
                off_peak=off_peak, notice=notice, session_id=session_id,
            )
        product_cards, structured_facts = self._product_layer(request.question)
        if live_price_request:
            # Do not reuse the legacy illustrative competitor figures for a live-price question.
            product_cards = [
                card.model_copy(update={
                    "competitor_price_inr": None,
                    "competitor_price_is_illustrative": None,
                })
                for card in product_cards
            ]
            if live_product is not None:
                product_cards = [self._to_card(live_product).model_copy(update={
                    "competitor_price_inr": None,
                    "competitor_price_is_illustrative": None,
                })]
                structured_facts = render_structured_facts("Kalakriti catalogue listing", [{
                    "product": live_product["name"], "Kalakriti_price_inr": live_product["price_inr"],
                    "region": live_product["region"], "city": live_product["city"],
                }])

        live_price, live_price_note = (None, None)
        live_status = None
        illustrative_fallback: dict | None = None
        if live_price_request and live_product is not None:
            try:
                live_price, live_price_note = retrieve_live_competitor_price(settings, live_product, request.question)
            except Exception as exc:  # noqa: BLE001 - live research must never break the chat
                logger.warning("Live competitor lookup failed (%s); continuing with the RAG answer.", type(exc).__name__)
                live_price, live_price_note = None, "Live competitor search is temporarily unavailable; no current price was verified."
            if live_price_note:
                live_price_note = live_price_note.rstrip(". ") + "."
            live_status = LivePriceStatus(
                verified=live_price is not None, product_id=live_product["product_id"], product_name=live_product["name"],
                message=None if live_price is not None else (live_price_note or "No current competitor price was verified."),
                checked_at=(live_price or {}).get("price_checked_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            if live_price is None:
                if live_product.get("competitor_price_inr") is not None:
                    # Fall back to the catalogue's own illustrative/academic reference figure -
                    # clearly labelled, never presented as a verified live price.
                    illustrative_fallback = {
                        "kalakriti_price_inr": live_product["price_inr"],
                        "illustrative_competitor_reference_price_inr": live_product["competitor_price_inr"],
                        "difference_inr": live_product.get("competitor_price_difference_inr"),
                    }
                    product_cards = [self._to_card(live_product).model_copy(update={
                        "competitor_price_inr": live_product["competitor_price_inr"],
                        "competitor_price_is_illustrative": True,
                    })]
                else:
                    live_price_note = (
                        f"No competitor/reference price information is available for {live_product['name']} "
                        "(neither a verified live price nor an illustrative academic figure)."
                    )

        t0 = time.perf_counter()
        if live_price_request and live_product is not None and request.filename is None:
            product_doc = f"{live_product['product_id']:02d}_{product_catalog.slugify_product_name(live_product['name'])}.docx"
            nodes = self.retrieve(
                request.question, department_slug="product", document_type=document_type,
                filename=product_doc, top_k=request.top_k,
            )
        else:
            nodes = self.retrieve(
                request.question, department_slug=department_slug, document_type=document_type,
                filename=request.filename, top_k=request.top_k,
            )
        retrieval_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "Retrieved %d chunks in %d ms (filters=%s, product_cards=%d, structured=%s)",
            len(nodes), retrieval_ms, applied or "none", len(product_cards), bool(structured_facts),
        )

        if not nodes and not structured_facts:
            self._store_turn(session_id, raw_question, INSUFFICIENT_INFO_ANSWER, [], [])
            return QueryResponse(
                answer=INSUFFICIENT_INFO_ANSWER, products=[], sources=[], grounded=False, retrieved_count=0,
                applied_filters=applied, model=None,
                timings=Timings(retrieval_ms=retrieval_ms, total_ms=int((time.perf_counter() - started) * 1000)),
                off_peak=off_peak, notice=notice, session_id=session_id,
            )

        nodes_in_context: list = []
        context_parts: list[str] = []
        history_block = render_conversation_history(recent_messages)
        if history_block:
            context_parts.append(history_block)
        if structured_facts:
            context_parts.append(structured_facts)
        if nodes:
            excerpts = [(i, n.node.metadata, n.node.get_content()) for i, n in enumerate(nodes, start=1)]
            excerpt_text, used = build_context(excerpts, settings.max_context_chars)
            nodes_in_context = nodes[:used]
            context_parts.append(excerpt_text)
        context = "\n\n".join(context_parts)

        t1 = time.perf_counter()
        system_prompt = SYSTEM_PROMPT
        if live_price_request:
            system_prompt = SYSTEM_PROMPT.replace(
                "Any competitor/market reference price is ILLUSTRATIVE / ACADEMIC DEMONSTRATION DATA, not verified real-world pricing. Say so plainly whenever you mention one - never present it as a real market quote.",
                "Synthetic competitor references in retrieved excerpts remain illustrative and must not be presented as live. Do not mention them in this response. The application will append a separately verified fetched web price, if available; never call that verified live price illustrative.",
            )
        try:
            answer = self.llm.generate(system_prompt, USER_TEMPLATE.format(question=request.question, context=context))
        except RAGError:
            if not (live_price_request and live_product is not None):
                raise
            # The live-price result is already verified server-side; still show it if the LLM is unavailable.
            logger.warning("LLM unavailable for a live-price question; returning the catalogue listing and lookup result.")
            answer = f"{live_product['name']} is listed on Kalakriti at ₹{live_product['price_inr']:,}."
        if live_price_request:
            if live_product is None:
                answer += "\n\nPlease name one Kalakriti catalogue product so I can search for a comparable current price."
            elif live_price is not None:
                answer += (
                    f"\n\nLIVE COMPETITOR PRICE — {live_price['competitor_name']}: "
                    f"{live_price['competitor_product_name']} — ₹{live_price['competitor_price_inr']:,}. "
                    f"KALAKRITI PRICE — {live_product['name']}: ₹{live_product['price_inr']:,}. "
                    f"Comparison: {live_price['comparison_type'].replace('_', ' ')}. "
                    f"Source: {live_price['source_url']} (checked {live_price['price_checked_at']})."
                )
            elif illustrative_fallback is not None:
                diff = illustrative_fallback["difference_inr"]
                diff_text = f" (difference: ₹{diff:,.0f})" if diff is not None else ""
                answer += (
                    f"\n\n{live_price_note or 'A current live competitor price could not be verified.'} "
                    f"Illustrative / Academic Demonstration Data on file for {live_product['name']}: "
                    f"Kalakriti price ₹{illustrative_fallback['kalakriti_price_inr']:,.0f} vs. illustrative "
                    f"competitor reference price ₹{illustrative_fallback['illustrative_competitor_reference_price_inr']:,.0f}"
                    f"{diff_text}. This reference figure is for academic demonstration only, not a verified market price."
                )
            else:
                answer += f"\n\n{live_price_note or 'A current comparable competitor price could not be verified.'}"
        generation_ms = int((time.perf_counter() - t1) * 1000)

        cited = extract_cited_ids(answer)
        insufficient = any(m in answer.lower() for m in _INSUFFICIENT_MARKERS)
        live_price_verified = live_price_request and live_price is not None
        sources = [
            node_to_source(i, n, used=(i in cited) if cited else not insufficient, excerpt_chars=excerpt_chars)
            for i, n in enumerate(nodes_in_context, start=1)
        ]
        total_ms = int((time.perf_counter() - started) * 1000)
        final_products = [] if insufficient and not live_price_verified else product_cards
        self._store_turn(session_id, raw_question, answer, final_products, sources)
        return QueryResponse(
            answer=answer, products=final_products,
            live_competitor_prices=[live_price] if live_price_verified else [], live_price_status=live_status, sources=sources,
            grounded=not insufficient or bool(live_price_verified), retrieved_count=len(nodes),
            applied_filters=applied, model=settings.ollama_model,
            timings=Timings(retrieval_ms=retrieval_ms, generation_ms=generation_ms, total_ms=total_ms),
            off_peak=off_peak, notice=notice, session_id=session_id,
        )
