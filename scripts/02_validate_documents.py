#!/usr/bin/env python
"""Re-validate the Markdown against the sources and write reports/validation_report.md with review samples."""
import sys

import _bootstrap  # noqa: F401
from backend.ingest import main

if __name__ == "__main__":
    sys.exit(main(["validate", *sys.argv[1:]]))
