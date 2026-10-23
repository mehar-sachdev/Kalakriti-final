# Troubleshooting

Start with `python scripts/check_config.py` and `GET /health` (both show which dependency is failing, without secrets).

| Symptom | Likely cause | Fix |
|---|---|---|
| `No .env file found … Missing required setting(s)` | `.env` not created | `cp .env.example .env`, fill values |
| `password authentication failed` | wrong DB password | Supabase → Project Settings → Database → reset password; update `SUPABASE_DB_URL` |
| `Tenant or user not found` | pooler needs `postgres.<project-ref>` as the user | copy the Session-pooler string again |
| `Network is unreachable` / `Cannot assign requested address` (WSL) | direct DB host is IPv6-only | use the **Session pooler** URI (IPv4) |
| Password contains `@`, `#`, `/` and the URL is rejected | needs percent-encoding | `@`→`%40`, `#`→`%23`, `/`→`%2F` |
| Connection timeout | project paused (free tier), VPN/firewall | resume the project in the dashboard |
| `extension "vector" is not available` | pgvector not enabled | `python scripts/setup_database.py --apply` or *Database → Extensions → vector* |
| Ollama `401/403` | wrong/expired key | new key at ollama.com/settings/keys |
| Ollama `404 model not found` | model name typo/unavailable | `curl https://ollama.com/api/tags`, set `OLLAMA_MODEL` |
| Ollama `429` | free-plan session/weekly limit or 2nd concurrent request | wait; keep `LLM_MAX_CONCURRENCY=1`; use off-peak; smaller model |
| Empty answer from the model | reasoning model spent its budget thinking | `OLLAMA_THINK=low` or another model |
| `The model did not answer within …s` | cloud busy | retry; raise `OLLAMA_TIMEOUT_SECONDS` |
| `Model returned 768-d vectors but … expects 384` | changed `EMBEDDING_MODEL` without `EMBEDDING_DIM` / new table | set `EMBEDDING_DIM`, then `python -m backend.ingest index --reset` |
| `The index was built with […] but the configuration now says …` | embedding model changed | `--reset` (vectors from different models cannot be mixed) |
| Docling PDF fails with `torch` / model errors | incomplete install or offline first run | `pip install docling`; run once with internet (models are cached); temporary: `ENABLE_PARSER_FALLBACK=true` (flagged low fidelity) |
| Report shows `FALLBACK_PARSER` | Docling failed on that PDF | read the `PRIMARY_PARSER_FAILED` message next to it |
| `LOW_TEXT_RECALL` / `NUMBER_RECALL` warnings | content lost in conversion | open `reports/validation_report.md`, compare; scanned PDF → `DOCLING_DO_OCR=true` |
| `EMPTY_PAGE` warning | scanned page without text layer | enable OCR |
| A document is missing from answers | failed to parse, or not indexed | see `reports/parsing_report.md`; `GET /api/documents` shows `indexed`; re-run `python scripts/ingest.py` |
| Answer says "I could not find this information…" for something real | cut-off too high, or wording far from the text | try `SIMILARITY_CUTOFF=0.15`, ask more explicitly (name the product/region), run `evaluate.py --retrieval-only` |
| `/products` shows the wrong image for a product | Supabase's `image_url` is stale from the original (buggy) seeding | it self-heals automatically - `CatalogService.list_products()` always overrides the image with the corrected path from `data/metadata/products.json`; re-run `python scripts/seed_database.py` to fix it at the source too |
| Product page opens with the wrong item, or doesn't open from a chat link | `#product-<id>` deep link fired before `loadProducts()` finished | the widget polls for up to ~8s; if it still fails, check the browser console for a failed `/products` request |
| Chat widget shows no product cards for an obviously relevant question | the structured layer didn't detect an intent/facet for that phrasing | rephrase naming the region/city/craft or price explicitly; see `backend/rag/products.py::detect_intent/detect_facets` for what triggers |
| `429 rate_limited` on `/api/chat` | `QUERY_RATE_LIMIT_PER_MINUTE` reached | wait a minute or raise it |
| Outside off-peak window message | `OFFPEAK_ENFORCE=true` | wait, or set it to `false` |
| `pytest` skips integration tests | no `TEST_DATABASE_URL` / `OLLAMA_API_KEY` | expected; set them to run those tests |
| `ModuleNotFoundError: backend` | running from another directory | run from the project root, or use `python scripts/…` (they fix the path) |
| First chat question is slow | embedding model loading | happens once per server start |
| `POST /orders` returns 503 | no Supabase project configured for checkout | expected in local-catalogue mode; set `SUPABASE_URL`/`SUPABASE_KEY` and run `scripts/seed_database.py`, or treat checkout as out of scope for the demo |
| `index.html` still references an external image URL | a new hero/region/artisan visual was added without a local asset | run `python scripts/validate_site.py` - it fails the build on any external image URL; add the file under `frontend/images/` and reference it with a relative path |
| Contact form / cart drawer overflow slightly on narrow phones | pre-existing storefront CSS, confirmed unrelated to the chat widget (reproduces with the widget never opened) | known, not fixed here - out of scope for this project |

Logs: console and `logs/app.log` (rotating). Set `LOG_LEVEL=DEBUG` for detail; secrets remain masked.
