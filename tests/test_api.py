import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from backend.exceptions import DatabaseError, LLMError, NotFoundError, OffPeakRestricted
from backend.main import create_app
from backend.models.schemas import DepartmentInfo, DocumentInfo, ProductCard, QueryResponse, SourceDetail, StatsResponse
from backend.rag.engine import RAGEngine
from tests.fakes import FakeIndex, FakeLLM, FakeRegistry, node


class StubEngine:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.requests = response, error, []

    def query(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.response


class StubCatalog:
    def departments(self):
        return [DepartmentInfo(slug="product", name="Product", document_count=60, chunk_count=300)]

    def documents(self, department=None, document_type=None):
        return [DocumentInfo(document_id="product__02", source_filename="02_x.docx", source_path="product/02_x.docx",
                             department="Product", department_slug="product", file_type="docx", indexed=True)]

    def stats(self):
        return StatsResponse(documents_total=78, documents_indexed=78, chunks_total=388, by_department={"Product": 60},
                             by_file_type={"docx": 74, "xlsx": 4}, parsing={"success": 78}, embedding="e", llm_model="m",
                             source="database")

    def source_detail(self, document_id, include_markdown=False):
        if document_id != "product__02":
            raise NotFoundError(f"Unknown document '{document_id}'.")
        return SourceDetail(**self.documents()[0].model_dump(), markdown="# Body" if include_markdown else None)


class StubShop:
    def list_products(self):
        return [{"product_id": 2, "product_name": "Chikankari Embroidered Kurta", "image_url": "images/Uttar_Pradesh/2_chikankari_kurta.jpg"}]

    def create_order(self, order):
        return {"message": "Order created successfully", "remaining_stock": 9}

    def health(self):
        return "not_configured", "SUPABASE_URL / SUPABASE_KEY not set; serving the local product catalog."


OK = QueryResponse(answer="Answer [1]", products=[ProductCard(product_id=2, name="Chikankari Embroidered Kurta",
                    category="Textile", region="Uttar Pradesh", city="Lucknow", price_inr=2600,
                    image="images/Uttar_Pradesh/2_chikankari_kurta.jpg", url="#product-2")], sources=[], grounded=True, retrieved_count=1)


@pytest.fixture
def client_factory(make_settings, monkeypatch):
    from backend.api import routes

    monkeypatch.setattr(routes, "check_database", lambda s: ("ok", None))
    monkeypatch.setattr(routes, "check_ollama", lambda s: ("ok", None))

    def factory(engine=None, **settings_kw):
        s = make_settings(supabase_db_url="postgresql://u:p@h/db", ollama_api_key="k" * 12, query_rate_limit_per_minute=0, **settings_kw)
        app = create_app(s, engine=engine or StubEngine(OK), catalog=StubCatalog(), shop=StubShop())
        return TestClient(app), app.state.rag
    return factory


def test_health_reports_components_and_never_secrets(client_factory):
    client, _ = client_factory()
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert set(body["components"]) == {"api", "config", "rag_database", "llm", "storefront_data", "embeddings"}
    text = client.get("/health").text
    assert "postgresql://" not in text and "k" * 12 not in text


def test_health_stays_ok_even_when_rag_database_not_configured(make_settings, monkeypatch):
    """The storefront (products/orders) must work even before Supabase/Ollama are set up."""
    from backend.api import routes

    monkeypatch.setattr(routes, "check_database", lambda s: ("not_configured", "SUPABASE_DB_URL is not set."))
    monkeypatch.setattr(routes, "check_ollama", lambda s: ("not_configured", None))
    app = create_app(make_settings(), engine=StubEngine(OK), catalog=StubCatalog(), shop=StubShop())
    r = TestClient(app).get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


# ---------------------------------------------------------------------------- storefront (public, no key)
def test_products_endpoint_unchanged_field_shape(client_factory):
    client, _ = client_factory()
    r = client.get("/products")
    assert r.status_code == 200
    row = r.json()[0]
    assert row["product_id"] == 2 and row["image_url"] == "images/Uttar_Pradesh/2_chikankari_kurta.jpg"


def test_region_hierarchy_endpoint_preserves_six_regions(client_factory):
    client, _ = client_factory()
    data = client.get("/api/regions").json()
    assert {region["region"] for region in data} == {
        "Uttar Pradesh", "Jammu & Kashmir", "Gujarat", "Rajasthan", "West Bengal", "Bihar",
    }
    rajasthan = next(region for region in data if region["region"] == "Rajasthan")
    assert any(city["city"] == "Udaipur" for city in rajasthan["cities"])


def test_orders_endpoint(client_factory):
    client, _ = client_factory()
    r = client.post("/orders", json={
        "order_id": "o1", "customer_id": "c1", "total_amount": 2600, "shipping_city": "Delhi", "shipping_state": "DL",
        "item": {"product_id": 2, "quantity": 1, "unit_price": 2600, "subtotal": 2600},
    })
    assert r.status_code == 200 and r.json()["message"] == "Order created successfully"


def test_orders_validation_error(client_factory):
    client, _ = client_factory()
    r = client.post("/orders", json={"order_id": "o1"})
    assert r.status_code == 422


def test_products_and_orders_need_no_api_key_even_when_one_is_set(client_factory):
    client, _ = client_factory(app_api_key="secret-admin-key")
    assert client.get("/products").status_code == 200


# ---------------------------------------------------------------------------- chat
def test_chat_happy_path(client_factory):
    engine = StubEngine(OK)
    client, _ = client_factory(engine)
    r = client.post("/api/chat", json={"question": "Tell me about the Chikankari Embroidered Kurta"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Answer [1]" and body["products"][0]["product_id"] == 2
    assert body["products"][0]["url"] == "#product-2"


def test_chat_needs_no_api_key(client_factory):
    client, _ = client_factory(app_api_key="secret-admin-key")
    r = client.post("/api/chat", json={"question": "Tell me about a product"})
    assert r.status_code == 200


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "a"}, {"question": 5}])
def test_chat_validation_errors(client_factory, body):
    client, _ = client_factory()
    assert client.post("/api/chat", json=body).status_code == 422


def test_chat_overlong_question_rejected(client_factory):
    client, _ = client_factory(max_question_chars=50)
    r = client.post("/api/chat", json={"question": "x" * 51})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("error,status,code", [
    (DatabaseError("db down", hint="check url"), 503, "database_error"),
    (LLMError("model busy", hint="retry"), 502, "llm_error"),
    (OffPeakRestricted("closed", hint="try later"), 429, "off_peak_restricted"),
    (RuntimeError("secret internals postgresql://u:pw@h"), 500, "internal_error"),
])
def test_chat_errors_map_to_http_statuses(client_factory, error, status, code):
    client, _ = client_factory(StubEngine(error=error))
    client = TestClient(client.app, raise_server_exceptions=False)
    r = client.post("/api/chat", json={"question": "What is the price?"})
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert "secret internals" not in r.text and "pw@h" not in r.text


def test_chat_missing_credentials_gives_503_with_setup_hint(make_settings):
    app = create_app(make_settings(), engine=StubEngine(OK), catalog=StubCatalog(), shop=StubShop())
    r = TestClient(app).post("/api/chat", json={"question": "What is the price?"})
    assert r.status_code == 503 and "SUPABASE_DB_URL" in r.json()["error"]["message"]


def test_chat_rate_limit(make_settings, monkeypatch):
    from backend.api import routes

    monkeypatch.setattr(routes, "check_database", lambda s: ("ok", None))
    s = make_settings(supabase_db_url="postgresql://u:p@h/db", ollama_api_key="k" * 12, query_rate_limit_per_minute=2)
    client = TestClient(create_app(s, engine=StubEngine(OK), catalog=StubCatalog(), shop=StubShop()))
    codes = [client.post("/api/chat", json={"question": "What is the price?"}).status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429]


# ---------------------------------------------------------------------------- catalog (categories/documents/stats/sources)
def test_catalog_endpoints(client_factory):
    client, _ = client_factory()
    assert client.get("/api/categories").json()[0]["slug"] == "product"
    assert client.get("/api/documents", params={"category": "product"}).json()[0]["document_id"] == "product__02"
    assert client.get("/api/stats").json()["documents_indexed"] == 78
    assert client.get("/api/sources/product__02", params={"include_markdown": "true"}).json()["markdown"] == "# Body"
    r = client.get("/api/sources/nope")
    assert r.status_code == 404


# ---------------------------------------------------------------------------- admin (gated)
def test_ingest_disabled_by_default_requires_no_key_to_learn_that(client_factory):
    client, _ = client_factory()
    r = client.post("/api/ingest", json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "feature_disabled"


def test_ingest_requires_api_key_when_one_is_configured(client_factory):
    client, _ = client_factory(app_api_key="secret-admin-key", enable_ingest_api=True)
    r = client.post("/api/ingest", json={})
    assert r.status_code == 401
    r = client.post("/api/ingest", json={}, headers={"X-API-Key": "secret-admin-key"})
    assert r.status_code == 202


# ---------------------------------------------------------------------------- static frontend
def test_frontend_index_served_at_root(client_factory):
    client, _ = client_factory(frontend_dir=Path("frontend"))
    r = client.get("/")
    assert r.status_code == 200 and "kalakriti" in r.text.lower()


def test_frontend_images_served(client_factory):
    client, _ = client_factory(frontend_dir=Path("frontend"))
    r = client.get("/images/Uttar_Pradesh/2_chikankari_kurta.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


def test_security_headers_present(client_factory):
    client, _ = client_factory()
    assert client.get("/health").headers["x-content-type-options"] == "nosniff"


def test_cors_only_allows_configured_origins(client_factory):
    client, _ = client_factory(cors_origins="http://localhost:8000")
    ok = client.options("/api/chat", headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "POST"})
    bad = client.options("/api/chat", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert "access-control-allow-origin" not in bad.headers


def test_cors_allows_any_ngrok_subdomain_without_hardcoding_one(client_factory):
    """ngrok's free tier hands out a fresh random subdomain every time the tunnel restarts, so this
    must accept the *pattern*, not one specific URL - and must still reject non-ngrok origins."""
    client, _ = client_factory(cors_origins="http://localhost:8000")
    free_tier = client.options("/api/chat", headers={"Origin": "https://abc123.ngrok-free.app", "Access-Control-Request-Method": "POST"})
    legacy = client.options("/api/chat", headers={"Origin": "https://my-tunnel.ngrok.io", "Access-Control-Request-Method": "POST"})
    still_local = client.options("/api/chat", headers={"Origin": "http://localhost:8000", "Access-Control-Request-Method": "POST"})
    impostor = client.options("/api/chat", headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"})
    assert free_tier.headers.get("access-control-allow-origin") == "https://abc123.ngrok-free.app"
    assert legacy.headers.get("access-control-allow-origin") == "https://my-tunnel.ngrok.io"
    assert still_local.headers.get("access-control-allow-origin") == "http://localhost:8000"
    assert "access-control-allow-origin" not in impostor.headers


# ---------------------------------------------------------------------------- full stack with real engine, fake LLM/index
def test_full_stack_with_fake_index_returns_structured_product_cards(make_settings):
    s = make_settings(supabase_db_url="postgresql://u:p@h/db", ollama_api_key="k" * 12, query_rate_limit_per_minute=0, similarity_cutoff=0.1)
    engine = RAGEngine(s, embed_model=object(), vector_store=object(), registry=FakeRegistry(), llm_gateway=FakeLLM("Answer [1]."))
    engine._index = FakeIndex([node("Chikankari kurta details.", 0.8, dept="product", dept_name="Product", code=None,
                                    doc="02_chikankari_embroidered_kurta.docx", page=None)])
    app = create_app(s, engine=engine, catalog=StubCatalog(), shop=StubShop())
    body = TestClient(app).post("/api/chat", json={"question": "Show me handmade products under ₹3000"}).json()
    assert body["products"] and all(p["price_inr"] <= 3000 for p in body["products"])
