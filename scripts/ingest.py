#!/usr/bin/env python
"""Full ingestion: parse -> validate -> chunk -> embed -> store in Supabase pgvector.
Alias of ingest_documents.py / `python -m backend.ingest all`, named to match the assignment brief."""
import sys

import _bootstrap  # noqa: F401
from backend.ingest import main

if __name__ == "__main__":
    sys.exit(main(["all", *sys.argv[1:]]))
