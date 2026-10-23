import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_frontend_has_city_step_filters_and_calls_generated_hierarchy():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="cityFilter"' in html
    assert 'fetch("/api/regions")' in html
    assert 'p.city===city' in html
    assert "Academic demo listing" in html
    assert 'width:min(450px,calc(100vw - 32px))' in html
    assert 'height:min(680px,calc(100vh - 80px))' in html
    assert "align-items:stretch;flex:1 1 0%;width:100%" in html
    assert "align-self:stretch;flex:0 0 auto" in html
    assert "width:100%;min-width:0" in html
    assert "overflow-wrap:normal" in html
    assert 'calc(100dvh - 20px)' in html
    assert "kaiLivePrices" in html
    assert "live_competitor_prices" in html
    assert re.search(r"window\.kaiLivePrices", html)
    assert "Competitor prices are illustrative.</div>" not in html
    assert "Live competitor prices are shown only when verified" in html
    assert "live_price_status" in html and "No current competitor price verified" in html
    assert "Verified on fetched page" in html and "vs. illustrative competitor price" not in html


def test_no_frontend_secret_or_external_product_image_reference():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "OLLAMA_API_KEY" not in html and "SUPABASE_DB_URL" not in html
    assert not re.search(r'https?://[^\s"\')]+\.(?:jpg|jpeg|png|svg|webp|gif)\b', html, re.I)


def test_every_product_has_its_own_local_image():
    import json

    catalog = json.loads((ROOT / "data" / "metadata" / "products.json").read_text(encoding="utf-8"))
    images = [p["image"] for p in catalog]
    assert len(set(images)) == len(images) == 146  # no image shared by two products
    for p in catalog:
        path = ROOT / "frontend" / p["image"]
        assert path.is_file() and not p["image"].startswith("http"), p["image"]
        if path.suffix == ".svg":  # generated illustrations are labelled with their own product name
            assert p["name"].replace("&", "&amp;") in path.read_text(encoding="utf-8"), p["product_id"]
