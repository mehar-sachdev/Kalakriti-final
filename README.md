# Kalakriti AI - Handicraft Storefront + Grounded RAG Assistant

A real, working AI shopping assistant (**💬 Kalakriti AI**) integrated directly into the existing Kalakriti
handicrafts storefront. It answers product, region, craft and price-comparison questions from a document
corpus using **Docling** (parsing), **LlamaIndex** (chunking/retrieval), **Supabase Postgres + pgvector**
(vector store), and **Ollama Cloud** (`gpt-oss:20b`, generation) - and renders real, working product cards
that open the storefront's own product view.

> This project modifies and extends an existing Kalakriti project. See
> [docs/project_report.md](docs/project_report.md) for exactly what was supplied vs. built, the bugs found
> and fixed (including one in the pre-existing code), and an honest verification status for every claim below.
>
> **Security note:** the uploaded project contained a real-looking Supabase key in `backend/.env`. It is not
> included anywhere in this project. **Rotate that key** in your Supabase dashboard.

## 1. Objective

Transform the storefront into an AI-enabled site where a shopper can ask "Which crafts come from Rajasthan?",
"Show me products under ₹3000", "Compare the Banarasi Silk Dupatta with the competitor reference price", or
"Where can I view the Dokra Tribal Lamp?" and get a grounded answer with real product cards and working links
- never an invented product, price, artisan, or "real" competitor figure.

## 2. Architecture

```
Kalakriti storefront (frontend/index.html)
        │  💬 Kalakriti AI widget → POST /api/chat (same origin)
        ▼
FastAPI (backend/main.py) — one process serves the site and the API
        │
        ├─ GET /products, POST /orders          legacy e-commerce API, preserved
        │                                        (Supabase REST, or local catalogue fallback)
        └─ POST /api/chat
                │
                ├─ Structured product layer (exact price filters/comparisons)
                └─ LlamaIndex retrieval → Supabase pgvector (Docling-parsed, BAAI/bge-small-en-v1.5)
                        │
                        ▼
                Ollama Cloud (gpt-oss:20b) → grounded answer + citations
                        │
                        ▼
        {answer, products[] (cards + #product-<id> links), sources[]}
```

Full diagram and design rationale: [docs/architecture.md](docs/architecture.md) ·
[docs/rag_pipeline.md](docs/rag_pipeline.md) · [docs/ingestion.md](docs/ingestion.md) ·
[docs/vector_database_comparison.md](docs/vector_database_comparison.md) (Supabase vs. Qdrant vs. Chroma).

## 3. Technology stack

Python 3.10+ · **Docling** (document parsing) · **LlamaIndex** (chunking, retrieval, query engine) ·
**BAAI/bge-small-en-v1.5** (local, free embeddings, 384-d) · **Supabase Postgres + pgvector** (HNSW, cosine) ·
**Ollama Cloud** (`gpt-oss:20b`) · **FastAPI** + Uvicorn · Pydantic v2 · SQLAlchemy 2 · `supabase-py` (legacy
storefront API) · the existing storefront's plain HTML/CSS/JS, extended with a vanilla-JS chat widget ·
pytest + Playwright (browser testing).

## 4. The existing Kalakriti frontend

`frontend/index.html` is the original storefront, preserved: branding, navigation, regions, product grid,
cart, checkout demo. Pre-existing bugs found and fixed while integrating: a hardcoded
`http://127.0.0.1:8000` fetch URL, 9/60 product images pointing at the wrong file, and every external
Unsplash stock-photo reference (hero/story backgrounds, 6 region-card photos, 3 artisan cards) replaced
with local, self-contained assets - the region cards now use the storefront's own real catalogue
photography, and the hero/story/artisan visuals are original brand-palette SVGs (see
`frontend/images/brand/`). The site now makes zero external network requests for any image. The
third-party Jotform chat widget and its hidden JSON knowledge block were removed and replaced with the
real, grounded assistant below. Full detail: [docs/project_report.md](docs/project_report.md).

## 5. Product data model

One authoritative source, `data/metadata/products.json` (built by `scripts/build_catalog.py` from the
storefront's own real product data + the real image files on disk), reused everywhere: the frontend's
product cards and modal, the RAG documents (`scripts/generate_documents.py`), the structured comparison
logic, and the chat widget's product cards. The 146 products carry: id, name, category/craft, region,
city, artisan, material, technique, description, price, availability, local image path, and a stable
`#product-<id>` URL. Existing competitor-reference figures are explicitly illustrative; new academic/demo
listings have no synthetic competitor price.

## 6. Region → City → Craft → Product

Built from the real `origin` field already in the product data (e.g. "Varanasi, Uttar Pradesh") - no
invented cities. `data/metadata/region_city_craft.json` holds the hierarchy; `documents/regional/*.docx`
document it region by region (e.g. Rajasthan → Jaipur/Jodhpur/Bagru/Kota/Sanganer/Pratapgarh, each with its
real crafts and representative products).

## 7. Document corpus (heterogeneous, real files)

```
documents/
        product/      146 DOCX (one per product) + products_catalog.xlsx
  competitor/   competitor_pricing.xlsx (every row labelled "Illustrative / Academic
                Demonstration Data") + methodology_note.docx (full disclaimer)
  regional/     6 DOCX, one per region
        craft/        9 DOCX, one per craft category
  artisan/      artisans_directory.xlsx
```
165 files, parsed by **Docling**, never typed as Python strings. Product entries marked Academic demo are
project concepts, not verified marketplace listings. Regenerate after editing source data:
`python scripts/build_catalog.py && python scripts/generate_documents.py`.

## 8. Chatbot integration

A floating **💬 Kalakriti AI** button opens a chat panel styled with the storefront's own design tokens
(colours, fonts) - not a generic developer widget. It shows a welcome message, example questions, a loading
state, product cards (image, price, illustrative competitor price struck through, region · city, a working
**View →** button), and clear error states with retry. Product links use the storefront's own in-page routing
(`#product-<id>` → the existing `openProduct()` modal); visiting that URL directly also opens the right
product on page load.

Explicit competitor/current-price questions for one named product use server-side Ollama Web Search/Web
Fetch. A live price is shown only when present on a fetched relevant page, with its source and check time;
if no live price can be verified but the catalogue has an illustrative/academic reference figure for that
product, that figure is shown instead, clearly labelled **"Illustrative / Academic Demonstration Data"**
(never presented as a verified market price); if neither is available, the chatbot says so plainly rather
than inventing a number. "Which products are cheaper than the competitor reference?" and "Which product has
the largest competitor price difference?" are multi-product questions and are always answered from the
structured catalogue data (`backend/rag/products.py`), not routed into the single-product live-price path.
Normal craft/product questions continue through the existing RAG path.

### Conversation memory

Every chat turn is stored in the database (`rag.conversations` / `rag.messages` - see §13), keyed by a
`session_id` the browser generates once per tab (`sessionStorage`, not `localStorage`) and sends with every
request. The server uses the most recently discussed product(s) to resolve follow-ups like *"What is its
price?"*, *"Tell me more about it."*, *"Is there a cheaper one?"* and *"Compare it with the competitor"* -
by rewriting the question (replacing the pronoun with the real product name) **before** it reaches the LLM,
so the existing retrieval/product logic needs no changes. If the conversation has two or more products on
the table and the user just says "it" with no other signal, the system does not guess which one - it leaves
the question as asked rather than silently picking one. A `which one is cheaper/more expensive` question
across several previously-shown products is resolved the same way, by comparing their real catalogue prices.
A database hiccup never breaks the chat: conversation storage/retrieval failures are logged and the chat
answers as if there were no history for that turn.

### Typo tolerance

Every question is run through `backend/rag/spelling.py` before retrieval: each word is fuzzy-matched
(RapidFuzz) against a vocabulary built dynamically from the live catalogue (product names, regions, cities,
crafts, materials, techniques, artisans) - not a hardcoded list of example typos. A word is only corrected
when it is not already a real catalogue word, not an ordinary English/retail word, not simply the regular
English plural of a valid word, and close enough to exactly one catalogue term. "Banarasi silk dupata" →
"...Dupatta", "Madubani painting" → "Madhubani...", "Rajashtan crafts" → "Rajasthan...", "Jaipur blue potery"
→ "...Pottery" - and ordinary words like "price", "compare", "boiling" are left alone.

### Mobile access via ngrok

See §15 below - the same FastAPI app, tunnelled, no second server and no hardcoded URL.

## 9. RAG grounding rules

The system prompt (`backend/rag/prompts.py`) requires: answer only from retrieved excerpts and computed
facts; never invent a product, price, artisan or competitor figure; say plainly when the knowledge base
doesn't have something; cite `[n]`; label every competitor price as illustrative, every time; report
conflicting sources rather than pick one silently. If nothing relevant is found, the LLM is not called at all
- a fixed, honest answer is returned instead.

## 10. Structured answers, not vector-search guesswork

Price filters ("under ₹3000") and competitor comparisons ("largest price difference") are answered by
`backend/rag/products.py`, computed exactly from the catalogue - never left to semantic similarity to get a
number right. See [docs/rag_pipeline.md](docs/rag_pipeline.md#product-aware-structured-layer) for how
intent/facet detection works and its deliberately conservative fallback behaviour.

## 11. Installation

```bash
cd kalakriti-final
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
The site works with **nothing configured** (local product catalogue, no chat yet) - open it right away:
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
→ http://127.0.0.1:8000/

## 12. Environment variables

Only two are required for the AI assistant (everything else has a sensible default - see `.env.example`
for the full, commented list):

| Variable | Required for | Where to get it |
|---|---|---|
| `SUPABASE_DB_URL` | the RAG vector store | Supabase → Project Settings → Database → Connection string (**Session pooler**) |
| `OLLAMA_API_KEY` | generation | ollama.com → Settings → Keys |
| `SUPABASE_URL` + `SUPABASE_KEY` | *optional*: real checkout (`/orders`) and Supabase-backed `/products` | Supabase → Project Settings → API |
| `NGROK_AUTHTOKEN` | *optional*: only if your ngrok account requires one | ngrok dashboard → Your Authtoken |

CORS already accepts any `*.ngrok-free.app` / `*.ngrok.io` / `*.ngrok.app` / `*.ngrok.dev` origin by default
(`CORS_ALLOW_ORIGIN_REGEX` in `.env.example`) - you do not need to add your tunnel's URL anywhere, and you
shouldn't, since ngrok's free tier gives you a new random one every time you restart it.

## 13. Database setup

```bash
python scripts/setup_database.py --apply
```
Creates a private `rag` schema (pgvector, HNSW index, RLS on, `anon`/`authenticated` revoked) - never touches
any pre-existing `products`/`orders` tables (see `sql/products_schema.sql` if you want those too, and
`scripts/seed_database.py` to populate them from the corrected local catalogue). The same schema also gets
two small tables for database-backed chat memory, `rag.conversations` and `rag.messages` (also RLS-enabled,
`anon`/`authenticated` revoked) - one migration, applied the same way, never touching the chunk/document
tables above.

## 14. Ingestion

The ZIP already ships the real, current `data/processed/*.md` + `manifest.json` (Docling's actual output
for all 165 documents, not a placeholder) so `python scripts/validate_site.py` works immediately with no
setup. That covers parsing only - the vector store itself lives in **your** Supabase project, so you still
need to embed and index once you've configured `SUPABASE_DB_URL`:

```bash
python scripts/parse_documents.py      # re-run only if you edit documents/ - Docling → data/processed/*.md
python scripts/validate_documents.py   # side-by-side samples in reports/validation_report.md
python scripts/ingest.py               # chunk + embed + store into YOUR Supabase pgvector (idempotent)
python scripts/validate_site.py        # image/link/document consistency check (auto-parses if needed)
```
Or in one step: `python scripts/ingest.py` (equivalent to `python -m backend.ingest all`; skips re-parsing
anything unchanged, so it goes straight to embedding/indexing using the shipped processed output).

## 15. Starting the server

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
→ **http://127.0.0.1:8000/** (storefront + chat) · `/docs` (API reference).

### Mobile access via ngrok

To open the live site on your phone (same storefront, same chatbot, one server, no separate frontend):

```bash
bash scripts/start_ngrok.sh
```

This script binds uvicorn to `0.0.0.0` (required for ngrok to reach it), starts an ngrok tunnel to it, reads
the public URL from ngrok's own local API (`http://127.0.0.1:4040/api/tunnels`) and **prints it** - it is
never hardcoded anywhere, because ngrok's free tier hands out a new random subdomain every restart. Open the
printed `https://....ngrok-free.app/` URL on your phone's browser: the full storefront loads, the 💬
Kalakriti AI button opens the same chat widget, and messages/responses/product cards/product links all work
exactly as on `127.0.0.1` - the frontend only ever calls relative paths (`/api/chat`, `/products`, ...), so
it automatically talks to whichever origin it was loaded from. Press `Ctrl+C` to stop both the API server and
the tunnel. Requires the `ngrok` CLI to be installed and on your `PATH` (https://ngrok.com/download); if your
ngrok account needs an authtoken, set `NGROK_AUTHTOKEN` in `.env` (never commit the real token) and the
script applies it automatically. Local access via `http://127.0.0.1:8000/` keeps working the whole time, in
parallel with the tunnel - nothing about `0.0.0.0` binding changes how localhost is reached.

If you'd rather run the two steps yourself:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000     # terminal 1
ngrok http 8000                                           # terminal 2 - copy the https URL it prints
```

## 16. Testing

```bash
pytest                                                        # 313 unit tests, no credentials needed
TEST_DATABASE_URL=postgresql://... pytest tests/integration   # +20 tests: real Postgres + pgvector, real 165-doc
                                                                #  corpus, conversation tables, scenarios A-G below
python scripts/test_rag.py                                    # live smoke test of the whole pipeline
```

### Testing conversation context (chat history)

With the server running and `SUPABASE_DB_URL` + `OLLAMA_API_KEY` configured, open the chat widget and ask,
in order: *"Tell me about the Banarasi Silk Dupatta."* → *"What is its price?"* → *"Is it cheaper than the
competitor?"*. Each answer should correctly refer to the Banarasi Silk Dupatta even though turns 2 and 3
never name it. Reloading the page keeps the same conversation (same tab); opening a new tab starts a fresh
one. To confirm it is really database-backed and not just browser state, check `rag.messages` in Supabase's
table editor - you will see the stored turns with their `product_ids`.

### Testing typo tolerance

Ask *"Tell me about the Banarasi silk dupata."*, *"Madubani painting"*, *"Rajashtan crafts"* and *"Jaipur
blue potery"* - each should be understood and answered as if spelled correctly. `pytest tests/test_spelling.py`
runs the same checks (plus negative cases - ordinary words and valid plurals are never "corrected") without
needing a server at all.

### Testing competitor prices

Ask *"Compare the Banarasi Silk Dupatta with competitor pricing"*, *"Which products are cheaper than the
competitor reference?"* and *"Which product has the largest competitor price difference?"*. Each should
return real catalogue figures, clearly labelled `Illustrative / Academic Demonstration Data`, never presented
as a verified market price; a product with no competitor data at all (some of the academic-demo items) says
so plainly instead of inventing one.

## 17. Validation

```bash
python scripts/validate_documents.py   # Markdown vs. source, side by side
python scripts/validate_site.py        # images, product links, document/catalogue consistency
python scripts/check_config.py         # what's configured, what isn't, with fix hints
```

## 18. Evaluation

```bash
python evaluation/evaluate.py --retrieval-only   # embeddings + pgvector, no LLM quota
python evaluation/evaluate.py                    # + Ollama Cloud answers
```
11 questions in `evaluation/questions.json`, every expected value computed from the real catalogue - see
[docs/evaluation.md](docs/evaluation.md). No results are shipped in this repository; the tool refuses to
fabricate a report.

## 19. Test questions to try in the chat widget

```
Tell me about the Banarasi Silk Dupatta.
What material is the Kashmiri Sozni Embroidered Shawl made from?
Which crafts come from Rajasthan?
Show me products from Jaipur.
Show me handmade products under ₹3000.
Which product has the largest competitor price difference?
Compare the Banarasi Silk Dupatta with the competitor reference price.
Where can I view the Dokra Tribal Lamp?
Show me products under ₹2000 from Bihar.
Tell me about the Kalakriti drone delivery program.        (should say it isn't in the knowledge base)
```

## 20. Troubleshooting

[docs/troubleshooting.md](docs/troubleshooting.md). First steps: `python scripts/check_config.py`,
`python scripts/test_rag.py`, `GET /health`, `logs/app.log`.

## 21. Known limitations

No per-user authentication (matches the original project); conversation memory is per `session_id`
(per-tab), not tied to a logged-in account, since there is no login system; follow-up resolution only
re-anchors on the most recently discussed product(s) - a bare "it" is left unresolved (and the question
answered as-is) once three or more products are on the table with no clearer signal, rather than guessing;
intent/facet detection is deliberately conservative and sometimes falls back to plain retrieval rather than
guess; competitor pricing is illustrative by design unless a live price was actually verified; a pre-existing
mobile layout overflow in the cart drawer/contact form was found but not fixed (confirmed unrelated to this
project's changes - see docs/project_report.md); ngrok's free tier URL changes every restart and is rate/
bandwidth-limited - fine for a demo, not a production deployment.

## 22. Future improvements

Real per-user authentication and order history tied to conversation memory; hybrid keyword+vector search; a
proper checkout flow wired to the corrected local catalogue when Supabase isn't configured; more evaluation
questions, especially ones exercising specific artisans and techniques; multilingual embeddings for Hindi
content; a paid/static ngrok domain (or a real deployment) instead of the free random-subdomain tunnel.

## 23. Repository layout

```
backend/            ingestion/ rag/ (incl. context.py, spelling.py) database/ (incl. conversations.py)
                     api/ models/ services/ config.py main.py ingest.py
frontend/            index.html (storefront + integrated chat widget, session-id aware) images/
documents/           product/ competitor/ regional/ craft/ artisan/  (165 generated DOCX/XLSX)
data/metadata/       products.json (authoritative catalogue), region_city_craft.json
data/processed/      generated by ingestion (git-ignored)
scripts/             build_catalog.py generate_documents.py validate_site.py parse/validate/ingest/
                     setup_database.py seed_database.py check_config.py test_rag.py query_cli.py
                     start_ngrok.sh _ngrok_tunnel_url.py
sql/                 products_schema.sql (legacy storefront tables, reference only)
supabase/migrations/ generated SQL for the RAG vector store + conversation tables (kept in sync by a test)
evaluation/          questions.json metrics.py evaluate.py
tests/               unit + integration (313 unit, +20 integration against a real database)
docs/                architecture, setup, ingestion, RAG design, vector-DB comparison, evaluation,
                     troubleshooting, project report (verification status)
```

## 24. Run in VS Code

Open the folder with `code .` (see `.vscode/` - tasks and launch configurations are pre-configured: Setup,
Check configuration, Ingest, Run API server, Tests). Press **F5** → "API server + open UI".

## 25. Reproduction summary

```bash
pip install -r requirements.txt
cp .env.example .env                       # fill in SUPABASE_DB_URL and OLLAMA_API_KEY
python scripts/setup_database.py --apply
python scripts/ingest.py
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
