import pytest

from backend.rag import products as P


@pytest.fixture(autouse=True)
def _fresh_cache():
    P.reset_cache()
    yield
    P.reset_cache()


def test_catalog_loads_all_sixty_products_with_required_fields():
    catalog = P.load_catalog()
    assert len(catalog) == 146
    assert len({p["product_id"] for p in catalog}) == 146
    required = {"product_id", "name", "category", "craft", "region", "city", "artisan", "material",
                "technique", "description", "price_inr", "competitor_price_inr", "image", "url"}
    for p in catalog:
        assert required <= set(p), p["product_id"]
        assert p["url"] == f"#product-{p['product_id']}"
        if p["availability"] == "Academic demo":
            assert p["competitor_price_inr"] is None


def test_every_catalog_image_file_exists_on_disk():
    """Requirement: no broken image references. Checked against the real files, not assumed."""
    frontend = P._CATALOG_PATH.parent.parent.parent / "frontend"
    missing = [p["image"] for p in P.load_catalog() if not (frontend / p["image"]).is_file()]
    assert missing == []


def test_competitor_price_always_labelled_illustrative_and_higher():
    for p in P.load_catalog():
        if p["competitor_price_inr"] is None:
            assert p["competitor_price_is_illustrative"] is False
            assert p["competitor_price_difference_inr"] is None
        else:
            assert p["competitor_price_is_illustrative"] is True
            assert p["competitor_price_inr"] > p["price_inr"]
            assert p["competitor_price_difference_inr"] == p["competitor_price_inr"] - p["price_inr"]


def test_hierarchy_uses_only_real_data_no_invented_cities():
    catalog_cities = {(p["region"], p["city"]) for p in P.load_catalog()}
    hierarchy_cities = {(r["region"], c["city"]) for r in P.load_hierarchy() for c in r["cities"]}
    assert hierarchy_cities == catalog_cities


def test_each_city_craft_branch_has_multiple_catalogue_products():
    for region in P.load_hierarchy():
        for city in region["cities"]:
            for craft in city["crafts"]:
                matches = P.filter_products(region=region["region"], city=city["city"], craft=craft)
                assert len(matches) >= 2, (region["region"], city["city"], craft)


def test_corrected_regions_have_coherent_demo_product_metadata_and_local_art():
    catalog = [p for p in P.load_catalog() if p["region"] in {"Rajasthan", "West Bengal", "Bihar"}]
    assert len(catalog) == 75
    for item in catalog:
        assert item["city"] and item["origin"].startswith(item["city"] + ", ")
        assert item["name"] in item["description"] and item["craft"].lower() in item["description"].lower()
        assert not item["image"].startswith(("http://", "https://"))
        if item["image"].endswith(".svg"):
            image = (P._CATALOG_PATH.parent.parent.parent / "frontend" / item["image"]).read_text(encoding="utf-8")
            assert item["name"] in image and "academic/demo" in image.lower()


def test_filter_by_region_city_craft():
    assert len(P.filter_products(region="Rajasthan", limit=50)) == 28
    jaipur = P.filter_products(city="Jaipur")
    assert {p["product_id"] for p in jaipur} == {31, 33, 36, 37, 97, 98, 99, 100, 136, 137}
    assert all(p["craft"] == "Pottery" for p in P.filter_products(craft="Pottery", region="Rajasthan"))


def test_filter_by_price():
    under = P.filter_products(max_price=3000)
    assert under and all(p["price_inr"] <= 3000 for p in under)
    over = P.filter_products(min_price=6000)
    assert over and all(p["price_inr"] >= 6000 for p in over)
    assert P.filter_products(max_price=1) == []


def test_cheaper_than_competitor_is_sorted_by_percentage_desc():
    items = P.cheaper_than_competitor(limit=60)
    assert len(items) == 60  # every product is cheaper than its (always-higher) illustrative reference
    pcts = [p["competitor_price_difference_pct"] for p in items]
    assert pcts == sorted(pcts, reverse=True)


def test_largest_price_difference_is_sorted_by_absolute_inr_desc():
    items = P.largest_price_difference(limit=5)
    diffs = [abs(p["competitor_price_difference_inr"]) for p in items]
    assert diffs == sorted(diffs, reverse=True)
    assert items[0]["competitor_price_difference_inr"] == max(
        abs(p["competitor_price_difference_inr"])
        for p in P.load_catalog() if p["competitor_price_difference_inr"] is not None
    )


def test_price_difference_for_one_product():
    d = P.price_difference(2)
    assert d["product_id"] == 2 and d["illustrative"] is True
    assert d["difference_inr"] == d["competitor_reference_price_inr"] - d["kalakriti_price_inr"]
    assert P.price_difference(9999) is None


@pytest.mark.parametrize("query,ids", [
    ("Tell me about the Chikankari Embroidered Kurta", [2]),
    ("Where can I view the Dokra Tribal Lamp?", [50]),
    ("What is the price of the Banarasi Silk Dupatta?", [1]),
    ("Show me the product", []),
    ("Tell me something not present in the knowledge base", []),
])
def test_find_by_name(query, ids):
    assert [p["product_id"] for p in P.find_by_name(query)] == ids


def test_find_by_name_longer_more_specific_match_ranks_first():
    # "Madhubani" alone would match several products; check specificity ordering still returns something sane
    hits = P.find_by_name("Madhubani Peacock Painting")
    assert hits and hits[0]["name"] == "Madhubani Peacock Painting"


def test_detect_facets_region_city_craft():
    assert P.detect_facets("Which crafts come from Rajasthan?") == {"region": "Rajasthan"}
    assert P.detect_facets("Show me products from Jaipur")["city"] == "Jaipur"
    assert P.detect_facets("What products use traditional weaving") == {}  # no exact craft-category name in this phrasing
    assert P.detect_facets("Jammu & Kashmir crafts")["region"] == "Jammu & Kashmir"
    assert P.detect_facets("nothing relevant here") == {}


@pytest.mark.parametrize("question,kind,extra", [
    ("Show me handmade products under ₹3000", "price_filter", {"max_price": 3000}),
    ("Show me products over ₹6000", "price_filter", {"min_price": 6000}),
    ("Which products are cheaper than the competitor reference?", "competitor_cheaper", {}),
    ("Which product has the largest competitor price difference?", "largest_diff", {}),
    ("Tell me about the Madhubani Wall Art.", "none", {}),
    ("What is the capital of France?", "none", {}),
])
def test_detect_intent(question, kind, extra):
    intent = P.detect_intent(question)
    assert intent.kind == kind
    for k, v in extra.items():
        assert getattr(intent, k) == v


def test_detect_intent_product_specific_diff_uses_matched_product():
    intent = P.detect_intent("Compare this product with the competitor reference.", matched_product_ids=[7])
    assert intent.kind == "product_diff" and intent.product_id == 7


def test_detect_intent_explicit_product_id_wins_over_matched_list():
    intent = P.detect_intent("Compare product 12 with the competitor price.", matched_product_ids=[7])
    assert intent.product_id == 12
