"""The pre-existing Kalakriti storefront API (``/products``, ``/orders``), preserved and made
resilient.

The original implementation (see the project this was built from) always called Supabase's
REST API via ``supabase-py`` and had no fallback: if ``SUPABASE_URL``/``SUPABASE_KEY`` were
unset, wrong, or the project was paused, the storefront's product grid stayed empty with no
way to demo the site. This version keeps the exact same Supabase-backed behaviour when it is
configured, and falls back to the local, authoritative ``data/metadata/products.json`` catalog
(the same one the RAG documents are generated from) when it is not - so the site and the
assistant always agree on product facts, and the storefront works out of the box before anyone
has touched Supabase.

This is deliberately a *separate* concern from the RAG vector store: this module never touches
the ``rag`` schema, and the RAG vector store (backend/database/) never touches the ``products``/
``orders`` tables. Two different credentials, two different jobs.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from backend.config import Settings
from backend.exceptions import ConfigurationError, DatabaseError
from backend.rag import products as product_catalog

logger = logging.getLogger(__name__)


def _client(settings: Settings):
    if not settings.supabase_url or settings.supabase_key is None:
        return None
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover
        raise ConfigurationError("The 'supabase' package is not installed.", hint="pip install supabase") from exc
    return create_client(settings.supabase_url, settings.supabase_key.get_secret_value())


def _local_product_row(p: dict) -> dict[str, Any]:
    """Shape a catalog entry exactly like a Supabase 'products' table row, so the frontend's
    existing field mapping (product_id, product_name, region, craft, ... image_url) is unchanged
    whichever source served it."""
    return {
        "product_id": p["product_id"], "product_name": p["name"], "region": p["region"], "craft": p["craft"],
        "material": p["material"], "technique": p["technique"], "origin": p["origin"], "artisan_id": p["artisan"],
        "price": p["price_inr"], "rating": p["rating"], "stock_quantity": 10, "image_url": p["image"],
        "description": p["description"], "status": "Active", "availability": p.get("availability", "In stock"),
    }


class CatalogService:
    """Wraps the legacy Supabase products/orders API with a local fallback."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        self._client_checked = False

    @property
    def client(self):
        if not self._client_checked:
            self._client = _client(self.settings)
            self._client_checked = True
        return self._client

    @property
    def source(self) -> str:
        return "supabase" if self.client is not None else "local"

    # ------------------------------------------------------------------ products
    def list_products(self) -> list[dict[str, Any]]:
        if self.client is not None:
            try:
                response = self.client.table("products").select("*").execute()
                rows = response.data or []
                if rows:
                    # The source-built local catalogue now includes corrected metadata and new
                    # demo items; older Supabase seeds may still contain stale fields or only 60
                    # products. Keep its live stock/status but use source data for product facts.
                    remote_by_id = {row.get("product_id"): row for row in rows}
                    catalog = product_catalog.load_catalog()
                    merged = []
                    for product in catalog:
                        local = _local_product_row(product)
                        remote = remote_by_id.get(product["product_id"], {})
                        local["stock_quantity"] = remote.get("stock_quantity", local["stock_quantity"])
                        local["status"] = remote.get("status", local["status"])
                        merged.append(local)
                    return merged
                logger.warning("Supabase 'products' table returned 0 rows; falling back to the local catalog.")
            except Exception as exc:  # noqa: BLE001 - any Supabase/network error falls back, never crashes the storefront
                logger.warning("Supabase products query failed (%s); falling back to the local catalog.", exc)
        return [_local_product_row(p) for p in product_catalog.load_catalog()]

    def get_product(self, product_id: int) -> Optional[dict[str, Any]]:
        return next((p for p in self.list_products() if p.get("product_id") == product_id), None)

    # ------------------------------------------------------------------ orders (Supabase only - a
    # local JSON catalog has no stock ledger to safely decrement, so this is refused with a clear
    # error rather than silently pretending to place an order).
    def create_order(self, order: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            raise DatabaseError(
                "Orders require a configured Supabase project (checkout is not available in local-catalog mode).",
                hint="Set SUPABASE_URL and SUPABASE_KEY in .env, then run backend/seed_database.py.",
            )
        try:
            order_response = self.client.table("orders").insert({
                "order_id": order["order_id"], "customer_id": order["customer_id"],
                "total_amount": order["total_amount"], "shipping_city": order["shipping_city"],
                "shipping_state": order["shipping_state"], "order_status": "Pending", "payment_status": "Pending",
            }).execute()
            item = order["item"]
            item_response = self.client.table("order_items").insert({
                "order_id": order["order_id"], "product_id": item["product_id"], "quantity": item["quantity"],
                "unit_price": item["unit_price"], "subtotal": item["subtotal"],
            }).execute()
            product_response = (
                self.client.table("products").select("stock_quantity").eq("product_id", item["product_id"]).single().execute()
            )
            new_stock = product_response.data["stock_quantity"] - item["quantity"]
            self.client.table("products").update({"stock_quantity": new_stock}).eq("product_id", item["product_id"]).execute()
            inventory_response = self.client.table("inventory_transactions").insert({
                "product_id": item["product_id"], "order_id": order["order_id"], "transaction_type": "Sale",
                "quantity_change": -item["quantity"], "notes": "Stock reduced after customer order",
            }).execute()
            return {
                "message": "Order created successfully", "order": order_response.data, "order_item": item_response.data,
                "inventory_transaction": inventory_response.data, "remaining_stock": new_stock,
            }
        except (KeyError, TypeError) as exc:
            raise ConfigurationError(f"Order payload is missing a required field: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError(f"Order could not be created: {exc}") from exc

    def health(self) -> tuple[str, Optional[str]]:
        if self.settings.supabase_url is None or self.settings.supabase_key is None:
            return "not_configured", "SUPABASE_URL / SUPABASE_KEY not set; serving the local product catalog."
        if self.client is None:
            return "error", "Supabase client could not be created."
        try:
            self.client.table("products").select("product_id").limit(1).execute()
            return "ok", None
        except Exception as exc:  # noqa: BLE001
            return "error", f"Supabase products table unreachable: {exc}"[:200]
