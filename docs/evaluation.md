# Evaluation

`evaluation/evaluate.py` measures the **real, configured system** on `evaluation/questions.json`. It never invents
numbers: with missing credentials or an empty index it exits with an error and writes **no** report.

```bash
python evaluation/evaluate.py --dry-run             # validate the question file only
python evaluation/evaluate.py --retrieval-only      # embeddings + pgvector; uses no LLM quota
python evaluation/evaluate.py                       # + Ollama Cloud answers
python evaluation/evaluate.py --judge               # + LLM-as-judge (subjective; the same model judges itself)
```
Output: `reports/rag_evaluation.json` and `reports/rag_evaluation.md` (mode, models, chunk settings, corpus size, per-question table).

## Metrics

| Metric | Definition | Objective? |
|---|---|---|
| Hit rate @k | expected document (by `doc_code`/file name) appears among the top-k sources | yes |
| MRR | mean of 1/rank of the first expected document | yes |
| Context precision | share of retrieved chunks that come from expected documents | yes |
| Expected-document recall | share of the expected documents retrieved | yes |
| Category isolation | with a document category selected, *every* source belongs to it (filter-leak test; category here means product/competitor/regional/craft/artisan, not a product's region) | yes |
| Fact recall | required facts (each a list of acceptable spellings) present in the answer - string match | yes, but strict |
| Out-of-scope refusal | questions marked `should_refuse` end with the "I could not find this information..." answer | yes |
| Citation rate / validity | answers contain `[n]`; every `[n]` maps to a retrieved source | yes |
| Numeric grounding | numbers in the answer (₹ amounts, days…) that also occur in the retrieved text; the rest are listed as *ungrounded* | yes |
| Judge faithfulness | supported / (supported + unsupported) claims as counted by an LLM | **no** - subjective |
| Latency | mean, p50, p95 total; mean retrieval and generation ms | yes |
| Chunks retrieved | mean number of chunks passed on after cut-off and de-duplication | yes |

Numeric grounding is the most useful hallucination alarm here: an invented price shows up as an ungrounded number.
It cannot tell whether a grounded number is *used* correctly - read the per-question answers for that. Note that price-filter
and competitor-comparison questions are answered by the structured product layer (`backend/rag/products.py`), not
retrieval, so their numbers are exact by construction - `tests/integration/test_real_corpus_pipeline.py` checks this
directly against the real corpus, which is a stronger guarantee than this evaluation framework can give.

## Question file

```json
{ "id": "comparison-largest-diff", "category": "comparison",
  "question": "Which product has the largest competitor price difference?",
  "expected": {"filenames": ["14_kashmiri_sozni_embroidered_shawl.docx"]},
  "facts": [["2,020", "2020"]],
  "should_refuse": false }
```

The shipped set (`evaluation/questions.json`) has 11 questions covering: product lookup, product material,
region discovery ("crafts from Rajasthan"), city discovery ("products from Jaipur"), price filtering, competitor
comparison (both "largest difference across the catalogue" and "compare this specific product"), a product-link
question, a multi-product region+price question, and two out-of-scope questions (an invented feature, general
knowledge).

Every `expected`/`facts` value here was computed directly from `data/metadata/products.json` (see
`scripts/build_catalog.py`), not estimated - for example, product 14's competitor price difference of ₹2,020 is
genuinely the largest of all 60 products, checked with a one-line script, not asserted from memory. `filenames`
is used instead of `doc_codes` because these documents identify by Product ID, not a policy-style document code.
**Add your own questions after browsing the storefront** - especially ones that depend on a specific artisan
name or technique description, which this starter set does not exhaustively cover.

## Reading a result honestly

* 11 questions cannot prove quality; use them to find failures, then add questions for each failure class.
* Fact recall is string matching; a correct paraphrase may score low - open the answer in the JSON report.
* Retrieval scores depend on `SIMILARITY_CUTOFF`, chunk settings and the embedding model; change one thing at a time
  and re-run `--retrieval-only` (cheap, deterministic given the index).
* Compare like with like: the report header records embedding, LLM, chunk config, top-k and corpus size.

## Status of this repository's evaluation

The metrics code is unit-tested (`tests/test_evaluation_metrics.py`). The runner has been exercised end to end in
`--retrieval-only` mode against the **real 165-document corpus** on a local Postgres + pgvector, using the
deterministic *hash* (lexical, non-semantic) embedding - this proves the mechanics work and produces genuinely
computed numbers, but is not a measurement of real retrieval quality, since the hash embedding does not do
semantic matching (a hash-embedding run on real questions scored roughly 57% hit-rate; a real bge-small run
would be expected to score higher on the region/city questions in particular, since those depend on semantic
similarity to phrases like "Rajasthan" rather than the structured layer, which is exact regardless of the
embedding). **No evaluation has been run with the real `BAAI/bge-small-en-v1.5` embedding model or against
Ollama Cloud**, because the author's sandbox has no route to huggingface.co's model weights download at
evaluation time beyond what was already cached, nor to ollama.com. No fabricated results are reported here for
that reason - run `python evaluation/evaluate.py` yourself once `.env` is configured, and `reports/rag_evaluation.md`
becomes the authoritative source.
