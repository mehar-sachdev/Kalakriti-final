#!/usr/bin/env python
"""Run the whole ingestion: parse + validate + index."""
import sys

import _bootstrap  # noqa: F401
from backend.ingest import main

if __name__ == "__main__":
    sys.exit(main(["all", *sys.argv[1:]]))
