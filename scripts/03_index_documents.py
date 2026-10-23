#!/usr/bin/env python
"""Stage 3: chunk, embed and store the processed documents in Supabase pgvector."""
import sys

import _bootstrap  # noqa: F401
from backend.ingest import main

if __name__ == "__main__":
    sys.exit(main(["index", *sys.argv[1:]]))
