#!/usr/bin/env python
"""Create / verify the Supabase (Postgres + pgvector) schema.

    python scripts/setup_database.py --check              # connectivity + schema status
    python scripts/setup_database.py --apply              # run the migrations (idempotent)
    python scripts/setup_database.py --write-migrations   # regenerate supabase/migrations/*.sql
    python scripts/setup_database.py --print              # show the SQL

You can also paste supabase/migrations/*.sql into Supabase's SQL editor, or use the Supabase CLI.
"""
import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from sqlalchemy import text

from backend.config import PROJECT_ROOT, get_settings
from backend.database.connection import check_database, explain_db_error, get_engine
from backend.database.registry import DocumentRegistry
from backend.database.schema import render_migrations
from backend.exceptions import RAGError
from backend.logging_config import redact, setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    group.add_argument("--write-migrations", action="store_true")
    group.add_argument("--print", dest="show", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format, settings.log_dir)
    migrations = render_migrations(settings)
    try:
        if args.write_migrations:
            target = PROJECT_ROOT / "supabase" / "migrations"
            target.mkdir(parents=True, exist_ok=True)
            for name, sql in migrations.items():
                (target / name).write_text(sql, encoding="utf-8")
                print(f"wrote {target / name}")
        elif args.show:
            for name, sql in migrations.items():
                print(f"-- ===== {name}\n{sql}")
        elif args.apply:
            settings.require("index")
            engine = get_engine(settings)
            for name, sql in migrations.items():
                with engine.begin() as conn:
                    conn.exec_driver_sql(sql.replace("%", "%%"))
                print(f"applied {name}")
            print("Schema is ready.")
        else:
            status, detail = check_database(settings)
            print(f"database: {status}" + (f" - {detail}" if detail else ""))
            if status == "ok":
                registry = DocumentRegistry(get_engine(settings), settings)
                try:
                    rows = registry.list_documents()
                    print(f"registry: {len(rows)} indexed documents, {registry.chunk_total()} chunks; RLS on chunk table: {registry.rls_enabled()}")
                except RAGError as exc:
                    print(f"registry: not created yet ({exc.message[:80]}). Run with --apply.")
            return 0 if status == "ok" else 1
    except RAGError as exc:
        print(f"ERROR [{exc.code}]: {redact(exc.message)}\nHINT: {exc.hint or '-'}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
