from types import SimpleNamespace

import httpx

from backend.rag.products import find_best_partial_name
from backend.rag.web_prices import is_live_competitor_question, retrieve_live_competitor_price


def response(body):
    return SimpleNamespace(json=lambda: body, raise_for_status=lambda: None)


def product():
    return {
        "name": "Jaipur Blue Pottery Bowl", "city": "Jaipur", "region": "Rajasthan", "craft": "Pottery",
        "price_inr": 950,
    }


def test_normal_rag_questions_do_not_request_live_research():
    for question in (
        "What is Madhubani painting?", "Tell me about this product", "Explain a traditional craft",
        "Compare Madhubani and Kalighat painting styles",
    ):
        assert not is_live_competitor_question(question)
    assert is_live_competitor_question("Compare the Jaipur Blue Pottery Bowl with Khadi India")
    assert is_live_competitor_question("What is the current competitor price?")


def test_explicit_short_current_price_query_resolves_named_catalogue_product():
    question = "What is the current competitor price for Jaipur Blue Pottery?"
    assert is_live_competitor_question(question)
    match = find_best_partial_name(question)
    assert match is not None
    assert match["name"] == "Jaipur Blue Pottery Bowl" and match["product_id"] == 31


def test_uses_ollama_search_and_fetch_and_verifies_explicit_page_price(make_settings, monkeypatch):
    settings = make_settings(ollama_api_key="server-only-key")
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        if url.endswith("web_search"):
            return response({"results": [{"title": "Khadi India blue pottery bowl", "url": "https://khadiindia.gov.in/item/blue-bowl"}]})
        return response({"title": "Khadi India Blue Pottery Bowl", "content": "Handmade Jaipur blue pottery bowl. Price: ₹1,250. Available now."})

    monkeypatch.setattr(httpx, "post", fake_post)
    result, note = retrieve_live_competitor_price(settings, product(), "Compare the Jaipur Blue Pottery Bowl with Khadi India")

    assert note is None and result is not None
    assert result["competitor_name"] == "Khadi India"
    assert result["competitor_product_name"] == "Khadi India Blue Pottery Bowl"
    assert result["competitor_price_inr"] == 1250 and result["price_verified"] is True
    assert result["source_url"] == "https://khadiindia.gov.in/item/blue-bowl"
    assert result["comparison_type"] == "comparable_category"
    assert calls[0][2]["query"].startswith("Jaipur Blue Pottery Bowl Rajasthan Jaipur Pottery India INR price")
    assert calls[0][1]["Authorization"] == "Bearer server-only-key"
    assert calls[1][2] == {"url": result["source_url"]}


def test_refuses_unrelated_or_unpriced_results(make_settings, monkeypatch):
    settings = make_settings(ollama_api_key="server-only-key")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: response(
        {"results": [{"title": "Unrelated listing", "url": "https://shop.example/item"}]}
        if a[0].endswith("web_search") else
        {"title": "Unrelated listing", "content": "Price: ₹500"}
    ))
    result, note = retrieve_live_competitor_price(settings, product(), "Compare this product")
    assert result is None and "could not be verified" in note


def test_web_failure_is_graceful_and_disabled_mode_makes_no_request(make_settings, monkeypatch):
    settings = make_settings(ollama_api_key="server-only-key")

    def fail(*args, **kwargs):
        raise httpx.ReadTimeout("provider timeout")

    monkeypatch.setattr(httpx, "post", fail)
    result, note = retrieve_live_competitor_price(settings, product(), "Compare with competitors")
    assert result is None and "temporarily unavailable" in note

    disabled = make_settings(ollama_api_key="server-only-key", ollama_web_search_enabled=False)
    result, note = retrieve_live_competitor_price(disabled, product(), "Compare with competitors")
    assert result is None and "disabled" in note


def test_no_credentials_does_not_search_or_raise(make_settings, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network called")))
    result, note = retrieve_live_competitor_price(settings, product(), "Compare with competitors")
    assert result is None and "not configured" in note


def test_skips_shipping_and_discount_amounts_and_returns_evidence(make_settings, monkeypatch):
    settings = make_settings(ollama_api_key="server-only-key")
    page = ("Free shipping on orders above ₹499. Get ₹150 off today. "
            "Handmade Jaipur blue pottery bowl, hand painted. Price: ₹1,250. In stock.")
    monkeypatch.setattr(httpx, "post", lambda url, **k: response(
        {"results": [{"title": "Blue pottery bowl", "url": "https://shop.example/bowl"}]}
        if url.endswith("web_search") else {"title": "Jaipur Blue Pottery Bowl", "content": page}
    ))
    result, note = retrieve_live_competitor_price(settings, product(), "What is the current competitor price?")
    assert note is None and result["competitor_price_inr"] == 1250
    assert "₹1,250" in result["evidence"] and result["source_name"] == "shop.example"


def test_price_far_from_product_text_is_not_accepted(make_settings, monkeypatch):
    settings = make_settings(ollama_api_key="server-only-key")
    page = "Jaipur blue pottery bowl collection. " + ("Lorem ipsum dolor sit amet. " * 80) + "Gift card ₹2,000"
    monkeypatch.setattr(httpx, "post", lambda url, **k: response(
        {"results": [{"title": "Shop", "url": "https://shop.example/x"}]}
        if url.endswith("web_search") else {"title": "Homepage", "content": page}
    ))
    result, note = retrieve_live_competitor_price(settings, product(), "competitor price")
    assert result is None and "could not be verified" in note


def test_fetches_are_capped(make_settings, monkeypatch):
    settings = make_settings(ollama_api_key="server-only-key")
    fetched = []

    def fake_post(url, *, headers, json, timeout):
        if url.endswith("web_search"):
            return response({"results": [{"title": f"r{i}", "url": f"https://s{i}.example/p"} for i in range(5)]})
        fetched.append(json["url"])
        return response({"title": "Unrelated", "content": "nothing"})

    monkeypatch.setattr(httpx, "post", fake_post)
    retrieve_live_competitor_price(settings, product(), "competitor price")
    assert len(fetched) == 3
