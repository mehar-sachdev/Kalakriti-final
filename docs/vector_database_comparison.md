# Vector database comparison: Supabase (pgvector) vs Qdrant vs Chroma

Scope: a retail storefront's product/region/craft/competitor knowledge base - roughly **80 documents / a few
hundred chunks per category**, free-tier budget, category- and product-filtered search, hosted alongside the
site on a laptop or a small server.

> Vendor limits, prices and versions change. The specifics below reflect the author's knowledge at the time of writing
> and **must be re-checked on each vendor's page** before relying on them. Scores are a judgment against *this project's*
> criteria, not a general ranking.

## Summary

| Criterion (weight) | Supabase + pgvector | Qdrant | Chroma |
|---|---|---|---|
| **What it is** | PostgreSQL extension, managed by Supabase | Purpose-built vector engine (Rust); self-host or Qdrant Cloud | Python-first embedded/local store; client-server and cloud options exist |
| Metadata filtering for products/regions (5) | **5** - plain SQL `WHERE` on indexed JSONB keys; joins with the registry table | **5** - payload filters integrated into HNSW search, the best filtering story | 3 - `where` filters work, fewer index/planning controls |
| Cost at this scale (4) | **4** - free tier covers it; must watch inactivity pausing and storage limits | 4 - free cloud cluster or free self-host; self-host costs your time | **5** - free, local file |
| Operational simplicity (4) | **4** - nothing to run; connection string only | 3 - a second service to run/monitor (or a cloud account) | **5** - zero services for local use |
| Security controls (4) | **5** - RLS, roles, private schema, backups, TLS, familiar audit story | 4 - API keys, TLS, RBAC in cloud | 2 - minimal built-in auth for self-hosted servers |
| LlamaIndex integration (3) | 4 - `PGVectorStore` (metadata filters, hybrid, HNSW options) | 4 - `QdrantVectorStore` | 4 - `ChromaVectorStore` |
| Transactions and a document registry (3) | **5** - the same DB holds the registry; per-document delete/insert; SQL for stats | 2 - no relational layer; registry lives elsewhere | 2 - same |
| Scale headroom (2) | 4 - millions of vectors with HNSW; big filtered searches need care | **5** - built for scale, quantisation, sharding | 3 |
| Portability / lock-in (2) | 4 - it is just Postgres + an extension; any Postgres with pgvector works | 4 - open source, self-hostable | 4 |
| **Weighted total (max 135)** | **120** | 105 | 95 |

(Weighted total = Σ weight × score. With different weights - e.g. millions of vectors and strict latency SLOs -
Qdrant wins; for a throw-away prototype with no security needs, Chroma wins.)

## Notes on each option

**pgvector on Supabase.** Exact and approximate (HNSW, IVFFlat) search with cosine/L2/inner product. Because chunks and the
document registry are ordinary tables, filtering, deleting one document’s chunks, counting per category and
enforcing access (RLS, private schema) need no extra tooling. Caveats: an approximate index combined with a *very selective*
filter can return fewer than `k` rows unless the pgvector version supports iterative scans (0.8+) or the planner
picks an exact scan - fine for small per-category subsets, worth testing at scale; managed free projects have
storage/compute limits and may pause when idle; vector dimension for HNSW indexes is capped (2,000 for the `vector` type).

**Qdrant.** The most capable dedicated engine: filterable HNSW, sparse+dense hybrid, quantisation, multitenancy
patterns. The price is one more service (or account) and no relational side for the registry, manifest and stats -
you would keep those in a second store. Excellent when the corpus and query volume grow by orders of magnitude.

**Chroma.** Fastest to start: `pip install`, persist to a folder, no server. Good for notebooks and demos. For an
internal tool holding confidential policies you would still need to add authentication, backups, TLS and a registry
yourself, and hosted/HA options are younger than the alternatives.

## Decision

**Supabase + pgvector**, because (1) the assignment’s default and the cheapest hosted option that satisfies (2) real
per-product/region metadata filtering with SQL, (3) a relational registry for idempotent indexing, incremental updates
and statistics in the same database, and (4) database-level security (private schema, RLS, revoked roles) with
no extra infrastructure. At ~40 documents the performance difference between the three is immaterial; the deciding
factors are operations and security.

**When to revisit:** > ~5–10 M chunks or strict p95 latency targets under heavy filtered load → Qdrant;
purely local offline demo with no confidentiality requirement → Chroma. The code isolates the store behind
`backend/database/vector_store.py` (LlamaIndex `VectorStore`), so switching means a new factory plus re-indexing; the registry
would need an equivalent.
