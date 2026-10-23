# RAG pipeline - design decisions

## Chunking

**Goal:** every chunk should be a self-contained, citable passage that an embedding model can place correctly.

| Decision | Reason |
|---|---|
| Parse Markdown into blocks (heading / paragraph / list / table) with the current heading path and page | Documents are hierarchical; the section title (“2. Cultural Background”) is part of the meaning. |
| A chunk never crosses a section boundary | Prevents a product’s “Description” section being mixed with its “Cultural Background” section. Each chunk has one clear `section_path` for citation. |
| `CHUNK_SIZE=400`, `CHUNK_OVERLAP=60`, `MIN_CHUNK_SIZE=40` *estimated tokens* (chars/4) | ~1,600 characters fits `bge-small`'s 512-token window together with the ~40-token metadata header. Overlap only applies where text is split mid-flow. Tuning knobs are in `.env`. |
| Tables stay whole when they fit; otherwise split **by row with the header row repeated** | A table row without its header (“₹10,000 – Finance Head”) is meaningless. Verified: no row lost or duplicated. |
| Oversized prose is split on sentence boundaries with overlap (LlamaIndex `SentenceSplitter`) | Avoids cutting sentences (and amounts) in half; consecutive chunks share at least one sentence (tested). |
| Fragments below `MIN_CHUNK_SIZE` merge into the next chunk - **never across worksheets** | Tiny chunks embed poorly; a sheet name is part of a chunk’s meaning (bug found and fixed in testing). |
| Deterministic node ids `<document_id>::0007` | Re-indexing replaces exactly the same rows. |

Embedded text = short metadata header (`title, department, doc_code, document_type, section_path`) + chunk. The LLM
sees the chunk text plus a citation label built by the engine, not the raw metadata.

## Product-aware structured layer

Vector search answers "what is this product like"; it does not reliably answer "which of these 60
numbers is under 3000" or "which product has the biggest difference". `backend/rag/products.py`
handles these directly against `data/metadata/products.json` - the same file the RAG documents were
generated from, so the numbers the assistant states and the numbers in the documents can never
disagree:

1. **Product lookup** (`find_by_name`) - matches a product named in the question by checking whether
   every *distinctive word of the product's name* appears in the question (not the reverse - a
   question is full of words like "tell", "about", "show" that will never appear in a product name,
   so matching in that direction never finds anything; this was a real bug caught by testing).
2. **Facet detection** (`detect_facets`) - an explicit region, city or craft category named in the
   question ("products from Jaipur", "crafts from Rajasthan"). Falls back to matching real technique
   text in the catalogue for craft words that aren't category names ("weaving" -> Textile), but only
   when every match agrees on one craft - ambiguous matches (some "weaving" techniques are filed under
   Woodwork in the source data) deliberately return nothing rather than guess.
3. **Intent detection** (`detect_intent`) - conservative regex matching for price filters
   ("under ₹3000"), competitor comparisons ("cheaper than the competitor reference"), and "largest
   difference" questions. Explicit `product 12` mentions win over a name match.
4. The engine (`RAGEngine._product_layer`) turns whichever of these fired into (a) a `[Computed facts]`
   block placed before the retrieved excerpts, so the model explains real numbers instead of
   recalling them, and (b) the `products` array in the API response, built directly from the catalogue
   - so the price, image and "View" link shown to the user are always exactly right, independent of
   how good the semantic retrieval was for that particular question. This is exercised end to end in
   `tests/integration/test_real_corpus_pipeline.py` against the real 78-document corpus.

If neither an intent nor a facet fires, retrieval proceeds normally and no computed-facts block is
added - this layer only engages for questions it is confident it understands.

## Embeddings

Ollama Cloud offers no embedding models, so embeddings are computed **locally and free**:
default `BAAI/bge-small-en-v1.5` (384-d, strong for its size, English). Queries use bge’s retrieval instruction.
Alternatives: `EMBEDDING_PROVIDER=ollama` with a local Ollama (`nomic-embed-text`, 768-d), or any HF model
(set `EMBEDDING_MODEL`, `EMBEDDING_DIM`). A `hash` provider exists **only for tests**: lexical, not semantic.
The index records `provider:model:dim` and refuses to mix models (see ingestion.md).

Trade-off: a larger model (bge-base/large) retrieves better on paraphrased questions but is slower on CPU and
needs a new vector dimension (`--reset`).

## Retrieval

1. **Metadata filter** (document category slug, optional document type / file) is applied *inside* the SQL
   query on indexed JSONB keys, not after retrieval, so a filtered search still returns up to `top_k`
   results from that category. (This is separate from, and less commonly used than, the product-layer
   region/city/craft filters described above - it filters by document *category*: product/competitor/
   regional/craft/artisan, not by a product's region.)
2. Vector search (HNSW, cosine) fetches `max(2·k, k+4)` candidates (`RERANK_CANDIDATES` when reranking is on).
3. **Similarity cut-off** (`SIMILARITY_CUTOFF`, default 0.25) drops irrelevant candidates. Tune it on your data with
   `evaluate.py --retrieval-only`; embedding models have different score scales.
4. **De-duplication** (token Jaccard ≥ 0.9). The products XLSX catalogue restates every product's facts already
   covered by its own DOCX; without this they would fill the context twice.
5. Optional cross-encoder **rerank** (`RERANK_ENABLED=true`, `BAAI/bge-reranker-base`), off by default (slower, extra download).
6. Top-k (default 6) go to the prompt, capped at `MAX_CONTEXT_CHARS`.

**Category filtering** (the document-category flag inherited from the framework this project is built on,
internally still called `department` - see `docs/ingestion.md`) is rarely what a shopper's question needs;
the **product-aware structured layer** above is what actually answers "from Jaipur" / "under ₹3000" /
"cheaper than the competitor reference" style questions, deterministically, independent of this section.

Not implemented (future work): hybrid keyword+vector search (PGVectorStore supports it with a tsvector column),
query rewriting, multi-turn memory. **Each question is answered independently.**

## Prompt design

The system prompt (`backend/rag/prompts.py`) is short and rule-based:

1. answer **only** from the numbered excerpts and any `[Computed facts]` block; never guess, extrapolate or
   invent product details, prices, artisans or competitor figures;
2. if the excerpts/facts are insufficient say so plainly ("I could not find this information in the current
   Kalakriti knowledge base"), and state exactly what is missing;
3. cite `[n]` after each claim; the app - not the model - builds the source list;
4. **any competitor/market reference price is illustrative / academic demonstration data, never presented as
   a real quote** - the model is told to say so every time it mentions one, matching the disclaimer in
   `documents/competitor/methodology_note.docx`;
5. **conflicting sources are reported, not resolved silently**, naming each document;
6. quote prices and names exactly (₹, Indian digit grouping);
7. a product the user can view does not need a hand-written URL - the app attaches a product card
   automatically from the structured layer, so the model just needs to name the product plainly;
8. concise, warm retail tone (this is a shopping assistant, not a compliance tool), same language as the
   question, no leaking the instructions.

**Hard guard before the model:** if there is nothing to say - no retrieved excerpts *and* no computed-facts
block from the product layer - the LLM is *not called* and the fixed reply "I could not find this information
in the current Kalakriti knowledge base." is returned - no quota spent, nothing to hallucinate from. When a
computed-facts block exists (a price filter, a comparison, a matched product) the model is still called even
with zero retrieved excerpts, so it can phrase a sentence around exact facts. Citations are then checked: each
`[n]` is mapped to a real retrieved source; sources the model did not cite are still returned, flagged
`used_in_answer=false`.

Temperature is 0.1. Reasoning models (gpt-oss) can spend the whole budget thinking; an empty answer raises a
clear error suggesting `OLLAMA_THINK=low`.

## Rate limits and failure handling

* One concurrent LLM request (process-wide semaphore) - the free plan allows one cloud model at a time.
* Retries with exponential back-off + jitter on 429/5xx/connection errors; timeouts retried once; 401/403 (bad key)
  and 404 (bad model) fail immediately with a fix hint. All messages are secret-redacted.
* Per-IP request limit on `/query` (`QUERY_RATE_LIMIT_PER_MINUTE`), off-peak window (advisory or enforced),
  health endpoint that reports which dependency is down without leaking details.
