#!/usr/bin/env python
"""Ask a question from the terminal.

    python scripts/query_cli.py "What is the reimbursement policy?" --department Finance
"""
import argparse
import sys

import _bootstrap  # noqa: F401
from backend.config import get_settings
from backend.exceptions import RAGError
from backend.logging_config import redact, setup_logging
from backend.models.schemas import QueryRequest
from backend.rag.citations import render_sources_text
from backend.rag.engine import RAGEngine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--department")
    parser.add_argument("--document-type")
    parser.add_argument("--filename")
    parser.add_argument("--top-k", type=int)
    args = parser.parse_args()
    settings = get_settings()
    setup_logging("WARNING")
    try:
        settings.require("query")
        response = RAGEngine(settings).query(QueryRequest(
            question=args.question, department=args.department, document_type=args.document_type,
            filename=args.filename, top_k=args.top_k,
        ))
    except RAGError as exc:
        print(f"ERROR [{exc.code}]: {redact(exc.message)}\nHINT: {exc.hint or '-'}", file=sys.stderr)
        return 2
    print(f"\n{response.answer}\n\n--- Sources ---\n{render_sources_text(response.sources)}")
    print(f"\n(filters: {response.applied_filters or 'none'}; retrieval {response.timings.retrieval_ms} ms, generation {response.timings.generation_ms} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
