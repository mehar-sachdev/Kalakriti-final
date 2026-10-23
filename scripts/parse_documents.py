#!/usr/bin/env python
"""Stage 1+2: convert PDF/DOCX/XLSX in documents/ to Markdown, validate, write manifest + report.
Alias of 01_parse_documents.py, named to match the assignment brief."""
import sys

import _bootstrap  # noqa: F401
from backend.ingest import main

if __name__ == "__main__":
    sys.exit(main(["parse", *sys.argv[1:]]))
