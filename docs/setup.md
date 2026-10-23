# Setup (Windows + WSL2 Ubuntu, or any Linux/macOS)

## 1. Prerequisites

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip
python3 --version     # 3.10+
```

## 2. Python environment

```bash
cd ~/kalakriti-final
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```
First use downloads Docling's models and the embedding model (`BAAI/bge-small-en-v1.5`, ~130 MB) once from
the internet; cached afterwards.

## 3. Try it with nothing configured

The site works with **zero configuration**: it serves the storefront and `/products` from the local
catalogue (`data/metadata/products.json`, including 60 original catalogue products and the expanded academic/demo items).

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000/ - browse the storefront, open a product. The **💬 Kalakriti AI** button is
there but will show a clear "not configured" error until step 4/5 below are done (that is expected).

## 4. Configuration

```bash
cp .env.example .env
```
Fill in two things:

### 4a. Supabase Postgres + pgvector (for the RAG assistant)
1. supabase.com -> New project (save the database password).
2. Project Settings -> Database -> Connection string -> **Session pooler** (port 5432, works over IPv4).
3. `.env`: `SUPABASE_DB_URL=postgresql://postgres.<ref>:<PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres`
   (percent-encode special characters in the password: `@` -> `%40`).
4. `python scripts/setup_database.py --apply` (creates a private `rag` schema, pgvector, HNSW index,
   RLS - never touches any pre-existing `products`/`orders` tables).

### 4b. Ollama Cloud (for the RAG assistant's answers)
1. ollama.com -> Settings -> Keys -> create a key -> `.env`: `OLLAMA_API_KEY=...`
2. Confirm the model exists: `curl -s https://ollama.com/api/tags | grep '"name"'`; default `gpt-oss:20b`.
3. Free plan = one concurrent request + session/weekly limits; the backend already serialises calls and
   retries 429/5xx.

### 4c. Supabase REST (optional - only needed for checkout / `/orders`)
`SUPABASE_URL` + `SUPABASE_KEY` (anon key) from Project Settings -> API, create `products`/`orders`/
`artisans`/`inventory_transactions` tables (see `sql/products_schema.sql` for a starting point), then
`python scripts/seed_database.py` to populate them from the authoritative local catalogue. Not required
for the AI assistant or for browsing the site - `/products` falls back to the local catalogue either way.

Run `python scripts/check_config.py` any time to see what is/isn't configured, and `python scripts/test_rag.py`
for a live smoke test of the whole pipeline.

## 5. Build the RAG document corpus and index it

The 165 documents (product/competitor/regional/craft/artisan) already exist under `documents/`, generated
from `data/metadata/products.json`. To regenerate them (e.g. after editing a product) or to index them:

```bash
python scripts/parse_documents.py      # Docling: documents/ -> data/processed/*.md + manifest + report
python scripts/validate_documents.py   # re-check Markdown vs sources, writes reports/validation_report.md
python scripts/ingest.py               # parse + index in one step (chunk -> embed -> Supabase pgvector)
python scripts/validate_site.py        # image/link/document consistency check (run before you ship, too)
```
All idempotent - re-running skips unchanged documents.

## 6. Run

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open **http://127.0.0.1:8000/** - the storefront, now with a working AI assistant. API docs at `/docs`.

## 7. Tests and evaluation

```bash
pytest                                                          # ~260 tests, no credentials needed
TEST_DATABASE_URL=postgresql://... pytest tests/integration     # real Postgres + pgvector, real 165-doc corpus
python evaluation/evaluate.py --retrieval-only                  # needs Supabase + an index, no LLM quota
python evaluation/evaluate.py                                   # full run, needs Ollama Cloud
```
See [evaluation.md](evaluation.md) and [troubleshooting.md](troubleshooting.md).
