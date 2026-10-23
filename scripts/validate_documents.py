#!/usr/bin/env python
"""Re-validate the converted Markdown against the source documents and write
reports/validation_report.md with side-by-side samples. Alias of 02_validate_documents.py."""
import sys

import _bootstrap  # noqa: F401
from backend.ingest import main

if __name__ == "__main__":
    sys.exit(main(["validate", *sys.argv[1:]]))
