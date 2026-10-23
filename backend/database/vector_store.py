"""LlamaIndex PGVectorStore bound to Supabase Postgres."""
from __future__ import annotations

import logging

from llama_index.vector_stores.postgres import PGVectorStore

from backend.config import Settings
from backend.database.connection import explain_db_error, safe_identifier, to_async_url, to_sync_url
from backend.database.schema import INDEXED_METADATA_KEYS
from backend.exceptions import DatabaseError

logger = logging.getLogger(__name__)


def build_vector_store(settings: Settings) -> PGVectorStore:
    settings.require("index")
    url = settings.supabase_db_url.get_secret_value()  # type: ignore[union-attr]
    try:
        store = PGVectorStore(
            connection_string=to_sync_url(url),
            async_connection_string=to_async_url(url),
            schema_name=safe_identifier(settings.db_schema),
            table_name=safe_identifier(settings.vector_table),
            embed_dim=settings.resolved_embedding_dim,
            use_jsonb=True,
            hnsw_kwargs={  # a fresh dict every call: PGVectorStore pops keys from it
                "hnsw_m": 16, "hnsw_ef_construction": 64, "hnsw_ef_search": 40, "hnsw_dist_method": "vector_cosine_ops",
            },
            indexed_metadata_keys={(key, "text") for key in INDEXED_METADATA_KEYS},
            perform_setup=True,
            initialization_fail_on_error=True,
        )
        store._initialize()  # connect now so problems surface here, with a clear message
        return store
    except DatabaseError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise explain_db_error(exc) from exc
