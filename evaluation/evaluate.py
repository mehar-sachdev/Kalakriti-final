"""Runs evaluation/questions.json against a live RAGEngine and produces a
scored markdown report. Needs real Supabase + Ollama credentials to run for
real; `load_questions`/`render_markdown` are pure and covered by unit tests
without any live service.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import metrics as m

ROOT = Path(__file__).resolve().parent.parent


def load_questions(path: Path) -> list[dict]:
    """Load and validate the evaluation question set.

    Raises ValueError (never silently drops bad data) when:
    - a question is missing its required `id` or `question` field,
    - two questions share the same `id`,
    - a question claims `should_refuse` but also expects specific
      `doc_codes` to be retrieved - those two expectations contradict
      each other (a refusal has no "correct" source to cite).
    """
    raw = json.loads(Path(path).read_text())
    questions = raw.get("questions") if isinstance(raw, dict) else raw
    if not isinstance(questions, list):
        raise ValueError("questions file must contain a 'questions' list")

    seen_ids: set[str] = set()
    for q in questions:
        if "id" not in q or "question" not in q:
            raise ValueError(f"question is missing required 'id' or 'question' field: {q}")
        if q["id"] in seen_ids:
            raise ValueError(f"duplicate question id: {q['id']}")
        seen_ids.add(q["id"])
        if q.get("should_refuse") and q.get("expected", {}).get("doc_codes"):
            raise ValueError(
                f"question {q['id']}: should_refuse=True cannot also expect specific doc_codes"
            )
    return questions


def render_markdown(report: dict) -> str:
    env = report.get("environment", {})
    agg = report.get("aggregate", {})
    lines = [
        "# Kalakriti RAG Evaluation Report",
        "",
        f"- Generated: {report.get('generated_at')}",
        f"- Mode: {report.get('mode')}",
        f"- Embedding model: {env.get('embedding')}",
        f"- LLM model: {env.get('llm_model')}",
        f"- Chunking: {env.get('chunk_config')}",
        f"- top_k: {env.get('top_k')}  similarity_cutoff: {env.get('similarity_cutoff')}",
        f"- Documents indexed: {env.get('documents')}  Chunks indexed: {env.get('chunks')}",
        "",
        "## Aggregate results",
        "",
        "```json",
        json.dumps(agg, indent=2),
        "```",
        "",
        "## Per-question results",
        "",
    ]
    for r in report.get("results", []):
        lines.append(f"- `{r}`")
    lines += [
        "",
        "## Limits of this evaluation",
        "",
        "These scores come from automated string matching (does the retrieved "
        "document code/filename match the one we expected, does the answer "
        "text contain an expected fact phrase or citation) rather than human "
        "judgement of answer quality. String matching cannot tell a correct "
        "paraphrase from a subtly wrong one, and a short, confident-sounding "
        "answer can score well on citation checks while still missing nuance "
        "a person would catch. Treat these numbers as a directional signal "
        "for regressions between runs, not as a certified accuracy figure.",
    ]
    return "\n".join(lines)


def run(questions_path: Path, mode: str = "full") -> dict:
    """Execute every question against the real RAGEngine. Only importable
    (and only called) when Supabase/Ollama are actually configured - keeps
    this module importable for the pure unit tests above without those
    services present."""
    from backend.config import get_settings
    from backend.rag.engine import build_engine
    from backend.models.schemas import QueryRequest

    questions = load_questions(questions_path)
    settings = get_settings()
    engine = build_engine(settings)

    results: list[dict[str, Any]] = []
    for q in questions:
        started = time.monotonic()
        try:
            resp = engine.query(QueryRequest(question=q["question"]))
            sources = [s.model_dump() for s in resp.sources]
            elapsed_ms = (time.monotonic() - started) * 1000
            retrieval = m.retrieval_metrics(sources, q.get("expected", {}), k=settings.top_k)
            refused = m.is_refusal(resp.answer, bool(sources))
            fact_score, missing = m.contains_all_groups(resp.answer, q.get("fact_groups", []))
            result = {
                "id": q["id"],
                "category": q.get("category"),
                "should_refuse": q.get("should_refuse"),
                "refused": refused,
                "retrieved_count": len(sources),
                "total_ms": elapsed_ms,
                "fact_recall": fact_score,
                "missing_facts": missing,
                **retrieval,
            }
        except Exception as exc:  # noqa: BLE001 - report, don't crash the whole run
            result = {"id": q["id"], "error": str(exc)}
        results.append(result)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "environment": {
            "embedding": settings.embedding_model,
            "llm_model": settings.ollama_model,
            "chunk_config": f"{settings.chunk_size}/{settings.chunk_overlap}",
            "top_k": settings.top_k,
            "similarity_cutoff": getattr(settings, "similarity_cutoff", None),
            "documents": None,
            "chunks": None,
        },
        "aggregate": m.aggregate(results),
        "results": results,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Kalakriti RAG evaluation suite")
    parser.add_argument("--questions", default=str(ROOT / "evaluation" / "questions.json"))
    parser.add_argument("--out", default=str(ROOT / "evaluation" / "report.md"))
    args = parser.parse_args()

    report = run(Path(args.questions))
    Path(args.out).write_text(render_markdown(report))
    (Path(args.out).with_suffix(".json")).write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
