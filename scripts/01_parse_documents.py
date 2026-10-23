#!/usr/bin/env python
"""Stage 1+2: convert PDF/DOCX/XLSX to Markdown, validate, write manifest + parsing report."""
import sys

import _bootstrap  # noqa: F401
from backend.ingest import main

if __name__ == "__main__":
    sys.exit(main(["parse", *sys.argv[1:]]))
