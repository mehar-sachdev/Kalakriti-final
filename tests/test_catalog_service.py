from backend.services.catalog_service import CatalogService


class FakeProductsTable:
    def select(self, *_args):
        return self

    def execute(self):
        return type("Response", (), {"data": [
            {"product_id": 31, "product_name": "Stale product name", "image_url": "old.jpg", "stock_quantity": 3, "status": "Active"},
        ]})()


class FakeSupabase:
    def table(self, name):
        assert name == "products"
        return FakeProductsTable()


def test_stale_supabase_seed_is_merged_with_authoritative_catalog(make_settings):
    service = CatalogService(make_settings(supabase_url="https://example.supabase.co", supabase_key="test-key"))
    service._client = FakeSupabase()
    service._client_checked = True

    products = service.list_products()
    by_id = {item["product_id"]: item for item in products}

    assert len(products) == 146
    assert by_id[31]["product_name"] == "Jaipur Blue Pottery Bowl"
    assert by_id[31]["image_url"] == "images/Rajasthan/031_demo.svg"
    assert by_id[31]["stock_quantity"] == 3
    assert by_id[31]["availability"] == "In stock"
    assert by_id[146]["product_name"] == "Bagru Natural-Dye Hand-Printed Cotton Panel"
    assert by_id[146]["image_url"] == "images/Rajasthan/146_demo.svg"
    assert by_id[146]["availability"] == "Academic demo"
