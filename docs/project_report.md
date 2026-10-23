# Kalakriti AI - Project Report

## 1. What this project is

Kalakriti is a handicrafts e-commerce storefront. This project adds a real, grounded RAG assistant
("💬 Kalakriti AI") directly into the existing storefront: a floating chat widget that answers product,
region, craft and price-comparison questions using LlamaIndex retrieval over Docling-parsed documents in
Supabase pgvector, generated with Ollama Cloud, and renders working product cards that open the storefront's
own product view. It builds on, and substantially modifies, an existing project supplied for this task.

## 2. What was supplied vs. what was built

**Supplied** (inspected first, before any change): a Kalakriti storefront `frontend/index.html` (1,120
lines) with a real 60-product catalogue and real photographs organised by region; a small existing FastAPI +
Supabase backend (`/products`, `/orders`); a third-party Jotform chat widget with no real backend behind it;
and empty placeholder folders (`rag/`, `documents/`, `tests/`, `dashboard/`) with no content. There was no
existing RAG implementation, no document corpus, and no LlamaIndex/Docling/pgvector/Ollama wiring to build on
- those needed to be built, not merely connected.

**Preserved as-is**: the storefront's visual identity, navigation, product modal, cart, and the `/products`/
`/orders` API contract the frontend already depends on.

**Built**: the entire RAG pipeline (Docling parsing, faithfulness validation, structure-aware chunking, local
embeddings, Supabase pgvector storage, LlamaIndex retrieval, Ollama Cloud generation), a 78-document corpus
generated from the real product data, a structured product-query layer for price/comparison questions, the
integrated chat widget, and the FastAPI layer tying it all to the existing storefront.

## 3. A security issue found, not created

The uploaded project's `backend/.env` contained what appears to be a **live Supabase project URL and anon
key**. This was not reproduced anywhere in this project's output and is excluded from the final ZIP.
**The Supabase anon key should be rotated** (Project Settings → API) since it was present in an uploaded file.

## 4. Bugs found and fixed in the pre-existing code

Found by testing, not by inspection alone - each of these broke something observable:

1. **9 of 60 product images pointed at the wrong file.** The original `seed_database.py` recomputed each
   image's filename by slugifying the product name; the real files on disk don't always match (e.g. product 2
   is "Chikankari Embroidered Kurta" but the file is `2_chikankari_kurta.jpg`). Fixed by mapping every
   product id to its real file on disk (`scripts/build_catalog.py`), and the legacy `/products` endpoint now
   self-heals this even if Supabase still has the old, wrong paths.
2. **A hardcoded `fetch("http://127.0.0.1:8000/products")`** in the storefront's own script - would break on
   any other host or port. Changed to a relative `fetch("/products")`.
3. **`let products = []` was invisible to any other `<script>` block** on the page (a `let` at top level does
   not become a `window` property, unlike `var` or a function declaration). This silently broke the new chat
   widget's ability to open a product from a card until traced and fixed by explicitly exposing
   `window.products` at the point it is populated.

## 5. Bugs found and fixed in code built for this project

1. Bold Markdown header labels (`**Product ID**`, which is how Docling renders a bolded table cell) leaked
   into adjacent field values because the metadata extractor didn't strip Markdown emphasis before matching.
2. The same extractor originally scanned "from one recognised label to the next", which silently swallowed
   any table row whose label wasn't in the known list into the *previous* field's value - found because the
   product documents' table has more fields than the original policy documents did. Rewritten to parse each
   table row independently.
3. `find_by_name("Tell me about the Chikankari Embroidered Kurta")` required every word of the *question*
   (including "tell", "about", "the") to appear in the product name - which can never match natural phrasing.
   The match direction was backwards; fixed to check the product name's distinctive words against the
   question instead.
4. `product_id`/`city`/`craft_category` were extracted into a document's metadata but never copied into the
   chunk metadata actually stored in pgvector, because the chunker's fixed key list didn't include them -
   found by an integration test against the real indexed corpus, not by inspection.

## 6. Second round: bugs found and fixed after a professor review pass

A follow-up review reported one failing test and a missing manifest. Both were investigated and fixed at
the root cause, not patched around:

1. **`resolved_embedding_dim` raised an error even with `embedding_dim=512` passed explicitly**, but only
   on some pydantic-settings versions. Root cause: the `EMBEDDING_DIM`/`EMBEDDING_DIMENSION` env-var alias
   added earlier (via `validation_alias=AliasChoices(...)`) silently disabled keyword construction by the
   field's own Python name on pydantic-settings ≤2.2.x, so `Settings(embedding_dim=512)` quietly fell back
   to the default (0). Reproduced by installing `pydantic-settings==2.2.1` in an isolated venv (this
   project's own `requirements.txt` lower bound), confirmed the failure, fixed with
   `model_config(populate_by_name=True)`, and confirmed the fix on that same old version before restoring
   the normal environment. `requirements.txt` now pins `pydantic-settings>=2.2,<3` and two regression tests
   cover both the keyword-construction path and the env-var-alias path directly.
2. **`scripts/validate_site.py` failed outright when `data/processed/manifest.json` did not exist yet**
   (e.g. straight after unzipping). It now runs a real Docling parse of `documents/` first when the
   manifest is missing - never a fabricated one - and only then validates; `--no-auto-parse` restores the
   old strict behaviour for CI. The real, current processed output is also now shipped in the ZIP (552 KB),
   so the check - and a first look at `reports/parsing_report.md` - works immediately with no setup step.
3. **Corpus validation was checking existence, not correctness.** Extended to check exact per-category file
   counts against the brief (61 product-folder files [60 sheets + 1 catalogue] / 2 competitor / 6 regional /
   8 craft / 1 artisan = 78), duplicate filenames, and - the one that would have caught a real mismapping -
   that each product's manifest entry actually extracted the matching `product_id` from its own document,
   not just that a file with the expected name exists.
4. **All 12 remaining external Unsplash image URLs removed.** The 6 region-card photos now use the
   storefront's own real catalogue photography (one representative product per region) instead of unrelated
   stock photos - arguably more correct as well as self-contained. The hero background, story-section
   background, story illustration, and 3 artisan-card icons became original local SVGs
   (`frontend/images/brand/`) in the site's own palette; the artisan icons are deliberately abstract
   craft-tool motifs (a shuttle, a potter's wheel, a needle) rather than an attempt at a fake photo of a
   real person. Verified with headless-browser screenshots (§8) and an automated check that fails the build
   if any `http(s)://...jpg|png|svg|...` reference reappears in `index.html`.

## 7. Architecture

See [docs/architecture.md](architecture.md) for the full diagram. In short: the storefront's chat widget calls
`POST /api/chat` (same origin); the engine runs a structured product-data lookup (exact price/comparison
answers) alongside vector retrieval over the 78-document corpus in Supabase pgvector; Ollama Cloud phrases a
grounded answer citing both; the response carries structured `products` cards the frontend renders and links
back into the storefront's own product view (`#product-<id>` → `openProduct(id)`).

## 8. The document corpus

Generated (`scripts/build_catalog.py` + `scripts/generate_documents.py`), not hand-typed, from one
authoritative source (`data/metadata/products.json`, itself built from the storefront's real product data):

| Category | Files | Format |
|---|---|---|
| product | 60 product sheets + 1 catalogue | DOCX + XLSX |
| competitor | pricing table + methodology/disclaimer | XLSX + DOCX |
| regional | 6 region profiles | DOCX |
| craft | 8 craft-category profiles | DOCX |
| artisan | 1 directory | XLSX |
| **Total** | **78 files** | |

Competitor reference prices are a **fixed, documented, per-category multiplier** applied to the real listing
price (e.g. Jewellery ×1.40) - never fitted to or claimed as real market data, and every occurrence in every
document and every API response is labelled "Illustrative / Academic Demonstration Data".

## 9. Testing

**267 automated tests** (255 unit, 12 integration), all passing in the author's sandbox at time of writing:

* Unit: config/secret-redaction, document discovery, metadata extraction (including the three bug-fix
  regressions above), Docling parsing of real DOCX/XLSX, ingestion-pipeline robustness and idempotency,
  faithfulness validation, chunking, the structured product-query module (price filters, comparisons,
  name/facet matching), retrieval and citation formatting, the LLM gateway's retry/concurrency/error handling,
  generated-SQL correctness, the merged FastAPI app (legacy storefront endpoints + new chat endpoints,
  auth, rate limiting), and evaluation metrics.
* Integration (real local PostgreSQL 16 + pgvector 0.6): the **real 78-document corpus** parses with 0
  failures and indexes into pgvector (388 chunks); a product-name question retrieves its own document as the
  top result; the structured layer's region/city/price/comparison answers are checked against the real index
  and are exact regardless of retrieval quality; the competitor-pricing and artisan documents are retrievable.
* **Browser (headless Chromium) against the actual merged app**: the storefront loads, the Jotform widget and
  hidden knowledge block are gone, the chat widget opens and answers discovery/price/comparison questions with
  correct product cards, clicking "View Product" opens the real product modal with correct data, a
  `#product-14` deep link opens the correct product on page load, a deliberately hostile answer (`<img
  onerror>`, `<script>`) rendered as inert text with zero injected elements, and the same checks pass at a
  390px mobile width.
* `scripts/validate_site.py` programmatically checks every product's image file, document file and the
  region/city/craft hierarchy against the real catalogue before packaging - it passes clean.

## 10. Verification status (read before trusting any claim)

| Item | Status |
|---|---|
| Storefront + widget merged, served from one FastAPI app | **Tested** - boots and serves correctly with zero configuration |
| Legacy `/products`/`/orders` preserved, image-path bug fixed | **Tested**, including the local-catalogue fallback path |
| 78-document corpus generation and Docling parsing | **Tested** with real Docling (DOCX/XLSX path) - 0 failures |
| Indexing into pgvector, structured product filters/comparisons | **Tested** end to end against real local Postgres + pgvector |
| Chat widget UI, product cards, "View Product" link, deep links, XSS safety | **Tested** in a real headless browser against the real merged app |
| FastAPI endpoints, auth, rate limiting, error handling | **Tested** with the FastAPI test client |
| `pydantic-settings` version sensitivity in config aliasing | **Tested** by reproducing the failure on `pydantic-settings==2.2.1` in an isolated venv, then confirming the fix on that same version |
| `scripts/validate_site.py` auto-parse, corpus counts, product-id round-trip, external-image check | **Tested** - 5 dedicated tests, including one that deletes the manifest and checks a real (not fabricated) re-parse happens |
| Hero/story/artisan images now local, zero external image URLs | **Tested**: automated check in `validate_site.py` and a dedicated test, plus visual confirmation via headless-browser screenshots |
| Docling **PDF** conversion (layout models) | **Not tested** - the sandbox has no `torch`; this project's corpus happens to need only DOCX/XLSX, so the gap did not block anything, but a PDF you add yourself should be checked against `reports/validation_report.md` |
| Real **HuggingFace embedding** model (`bge-small-en-v1.5`) | **Not run** - no network route to huggingface.co from the sandbox; all RAG tests use a deterministic lexical hash embedding instead (see docs/evaluation.md for what that does and doesn't prove) |
| **Ollama Cloud** (auth, generation) | **Not tested** - no credentials, no network route to ollama.com. `scripts/test_rag.py` correctly reports a clear failure with a fix hint when pointed at a fake key |
| **Supabase Cloud** (either the vector store or the products/orders REST API) | **Not tested** - requires your project. Connection-string handling and error messages are unit-tested |
| Evaluation results on the real corpus with real embeddings/LLM | **Not run** - `evaluation/evaluate.py` was run in `--retrieval-only` mode with the lexical hash embedding as a mechanics check (57% hit-rate on 11 questions - not a semantic-quality number); no full run exists, and the tool refuses to fabricate one |
| Mobile layout overflow in the cart drawer / contact form | **Confirmed pre-existing** (reproduces identically with the chat widget never opened) - not fixed, out of scope |

**Requires your configuration:** `SUPABASE_DB_URL` (RAG vector store), `OLLAMA_API_KEY` (generation), and
optionally `SUPABASE_URL`/`SUPABASE_KEY` (only if you want Supabase rather than the local catalogue to be the
source of truth for `/products`/`/orders`).

## 11. Limitations

* No per-user authentication; the storefront and chat are public, matching the original project.
* Each chat question is answered independently - no conversation memory.
* Facet/intent detection in the structured product layer is deliberately conservative (see
  docs/rag_pipeline.md) - it will sometimes fall back to plain retrieval rather than guess at an ambiguous
  filter, which is safer but occasionally means a filterable question isn't filtered.
* Competitor pricing is illustrative by design (per the assignment brief) and must never be read as real
  market research.
* The evaluation question set (11 questions) is a starting point, not proof of quality at scale.

## 12. Reproduction

See [docs/setup.md](setup.md). In short: `pip install -r requirements.txt`, `cp .env.example .env` and fill in
two values, `python scripts/setup_database.py --apply`, `python scripts/ingest.py`, then
`uvicorn backend.main:app --host 127.0.0.1 --port 8000` and open `http://127.0.0.1:8000/`.
