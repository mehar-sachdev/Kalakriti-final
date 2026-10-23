# Ingestion

```
documents/<category>/**/*.{docx,xlsx,pdf,csv,txt,md}      category = product | competitor | regional | craft | artisan
        │  discover (dynamic categories, checksums)
        ▼
   Docling / text parser ──► clean ──► validate ──► data/processed/<category-slug>/<file>.md
        │                                                │
        └── failures recorded, batch continues           └── manifest.json / manifest.csv, reports/parsing_report.{json,md}
        ▼
   chunk ──► embed ──► Supabase pgvector + registry
```

This project's corpus (`documents/`) is generated, not hand-authored: `python scripts/build_catalog.py`
builds the single authoritative `data/metadata/products.json` from the storefront's real product data,
then `python scripts/generate_documents.py` writes 165 DOCX/XLSX files from it (146 product sheets +
1 catalogue XLSX, 6 regional profiles, 9 craft profiles, a competitor-pricing XLSX + methodology note,
and an artisan directory XLSX). Re-run both after changing a product; ingestion picks up the change like
any other edited document (checksum-based).

## Commands

| Command | What it does |
|---|---|
| `python -m backend.ingest list` (or `scripts/parse_documents.py --help`) | Show what would be processed. |
| `… parse [--department X] [--force]` | Convert to Markdown, validate, write manifest and reports. (The flag is still named `--department` internally - it means "category" here: product/competitor/regional/craft/artisan.) |
| `… validate [--sample N]` | Re-check Markdown vs current sources; write `reports/validation_report.md` with side-by-side samples. |
| `… index [--force] [--prune] [--reset]` | Chunk, embed, store. `--prune` drops vanished files; `--reset` rebuilds after an embedding-model change. |
| `… all` | parse + index. `--strict` makes any failure exit with status 1. |

Exit codes: 0 done, 1 done but `--strict` and something failed, 2 configuration/database error (message + hint
printed), 130 interrupted (progress is saved).

## Discovery

Every immediate sub-folder of `documents/` is a category (`product` → slug `product`).
Sub-folders inside a category are searched recursively. Hidden/temp files (`~$x.docx`, `.DS_Store`) are ignored;
unsupported types are listed as *skipped* in the report. Files placed directly in `documents/` are filed under
“Unassigned” with a warning. A document’s id is derived from its path, so editing a file keeps its id.

## Parsing details

* **PDF** - exported page by page, each page preceded by `<!-- page: N -->` so chunks can cite pages. Docling's
  Markdown export leaves out the page-furniture layer, so running headers/footers (“Page 2 of 3”) should not pollute the text -
  **not verified in the author's sandbox (PDF layout models need torch); check the first real PDFs in `reports/validation_report.md`.** OCR is off by default
  (`DOCLING_DO_OCR=true` for scans; flagged automatically as `EMPTY_PAGE` warnings when needed).
* **DOCX** - headings, lists, tables to Markdown. Word files often carry section titles as plain numbered
  paragraphs (“5.1 Business Travel”); if Docling found fewer than three headings these are promoted to real
  headings (`PROMOTE_NUMBERED_HEADINGS`), keeping the original numbering.
* **XLSX/XLS** - Docling models each sheet as a named group but its Markdown drops the names; the parser
  re-inserts `## Sheet: <name>` so answers can cite “Sheet: Approval Rules”.
* Docling’s default escaping of `_` and `&` is switched off to keep text searchable.
* **Fallback** (`ENABLE_PARSER_FALLBACK=true`, PDFs only): plain pdfium text if Docling fails. Lower fidelity;
  always flagged `FALLBACK_PARSER` in the manifest and report.

## Metadata

From the file system: category, filename, path, type, checksum, stable id. From each document's own header
table, parsed from Markdown tables *and* run-together text: for product/regional/craft documents that means
`Product ID`, `City`, `Craft Type`/`Craft Category`, `Region`, `Price (INR)`, `Availability`, `Product URL`
(see `HEADER_LABELS` in `backend/ingestion/metadata.py` and `scripts/generate_documents.py`, which writes these
exact header rows). These become chunk metadata (`NODE_DOCUMENT_KEYS` in `backend/rag/chunking.py`), so a
retrieved chunk always carries its `product_id`/`city`/`craft_category` even without semantic matching on
those words. The generic `Document ID`/`Version`/`Status` labels are also recognised, for any future document
that uses that convention (e.g. a formal policy imported from another project).

A real bug found and fixed while building this: Docling renders a *bolded* header-table cell as
`**Label**`; the original label-scanning code did not strip the `**`, so a bold label's closing marker
leaked into its own value and, worse, into the *next* row's value for any row whose label the code did not
recognise. Fixed by (1) stripping Markdown emphasis before matching, and (2) parsing each table row
independently rather than scanning from one recognised label to the next (see `tests/test_metadata.py`).

## Validation (faithfulness)

Every document is compared with text extracted by a *different* library (python-docx / openpyxl / pypdfium2):

| Check | Warning | Error |
|---|---|---|
| `word_recall` (distinct source words found in the Markdown) | < 97 % | < 85 % |
| `number_recall` (amounts, dates, limits) | < 98 % | < 85 % |
| Empty output | | yes |
| Encoding damage (U+FFFD, mojibake like `â‚¹`, control chars) | yes | |
| Malformed Markdown tables (no separator, ragged columns) | yes | |
| Table count lower than the source | yes | |
| Missing worksheet, page-marker mismatch, empty PDF page | yes | |
| No headings in a long DOCX/PDF | yes | |

Errors make the document *failed* (not indexed); warnings are kept and listed. Dates in spreadsheets are excluded
from number recall (they are rendered locale-specifically). Recall is a strong smoke alarm, not proof: read the
side-by-side samples for a few files per type.

## Idempotency and change handling

A document is re-parsed only if its checksum, the parser configuration (Docling version, OCR, headings, fallback),
the output file, or `--force` says so. It is re-indexed only if its checksum, chunk settings or embedding model
changed. Failed files are retried on the next run. Changing the **embedding model** is refused unless `--reset`
is given, because vectors from different models must never share a table.

## Extending

* New category: add a folder. New file type: add the extension to `SUPPORTED_EXTENSIONS` in `discovery.py`
  and a branch in `ParserRegistry.parse` (`parser.py`); add a reference extractor in `validator.py` if possible.
* Logs go to the console and `logs/app.log` (rotating), with secrets masked.
