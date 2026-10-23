"""Follow-up / pronoun resolution (backend/rag/context.py) - deterministic rewriting, not a
second LLM call, so the behaviour is fully testable without any model or database."""
from backend.rag import products as product_catalog
from backend.rag.context import has_referent, resolve_followup

# Product 1 = Banarasi Silk Dupatta (₹4,200). Used throughout as "the one thing already
# discussed" for the single-candidate cases.
DUPATTA_ID = 1
DUPATTA = product_catalog.get_product(DUPATTA_ID)


def test_has_referent_detects_common_pronoun_phrasings():
    for phrase in ["What is its price?", "Tell me more about it.", "Compare this product with competitors."]:
        assert has_referent(phrase)
    assert not has_referent("Tell me about the Banarasi Silk Dupatta.")


def test_no_history_leaves_the_question_unresolved():
    resolved = resolve_followup("What is its price?", [])
    assert resolved.question == "What is its price?" and not resolved.rewritten and resolved.resolved_product_id is None


def test_single_product_history_resolves_a_plain_pronoun():
    resolved = resolve_followup("What is its price?", [DUPATTA_ID])
    assert resolved.rewritten and resolved.resolved_product_id == DUPATTA_ID
    assert resolved.question == f"What is {DUPATTA['name']}'s price?"


def test_possessive_grammar_is_handled():
    resolved = resolve_followup("What is its price?", [DUPATTA_ID])
    assert f"{DUPATTA['name']}'s" in resolved.question


def test_tell_me_more_about_it_resolves_to_the_discussed_product():
    resolved = resolve_followup("Tell me more about it.", [DUPATTA_ID])
    assert resolved.rewritten and resolved.resolved_product_id == DUPATTA_ID
    assert DUPATTA["name"] in resolved.question


def test_competitor_followup_names_the_product():
    resolved = resolve_followup("Is it cheaper than the competitor?", [DUPATTA_ID])
    assert resolved.rewritten and DUPATTA["name"] in resolved.question


def test_ambiguous_multi_product_history_does_not_guess():
    # Two or more products on the table and a bare pronoun: genuinely ambiguous, must not guess.
    other_id = next(p["product_id"] for p in product_catalog.load_catalog() if p["product_id"] != DUPATTA_ID)
    resolved = resolve_followup("Tell me more about it.", [DUPATTA_ID, other_id])
    assert not resolved.rewritten and resolved.resolved_product_id is None
    assert resolved.question == "Tell me more about it."


def test_no_referent_and_no_superlative_is_a_no_op():
    resolved = resolve_followup("Show me products from Rajasthan.", [DUPATTA_ID])
    assert not resolved.rewritten and resolved.question == "Show me products from Rajasthan."


def test_cheaper_superlative_resolves_across_multiple_candidates():
    rajasthan_products = product_catalog.filter_products(region="Rajasthan", limit=20)
    ids = [p["product_id"] for p in rajasthan_products]
    cheapest = min(rajasthan_products, key=lambda p: p["price_inr"])

    resolved = resolve_followup("Which one is cheaper?", ids)
    assert resolved.rewritten
    assert resolved.resolved_product_id == cheapest["product_id"]
    assert cheapest["name"] in resolved.question


def test_pricier_superlative_resolves_to_the_more_expensive_candidate():
    rajasthan_products = product_catalog.filter_products(region="Rajasthan", limit=20)
    ids = [p["product_id"] for p in rajasthan_products]
    pricier = max(rajasthan_products, key=lambda p: p["price_inr"])

    resolved = resolve_followup("Which one is more expensive?", ids)
    assert resolved.rewritten and resolved.resolved_product_id == pricier["product_id"]


def test_duplicate_ids_in_history_are_deduped_safely():
    resolved = resolve_followup("What is its price?", [DUPATTA_ID, DUPATTA_ID, DUPATTA_ID])
    assert resolved.resolved_product_id == DUPATTA_ID


def test_scenario_d_chained_followups_from_the_brief():
    """D. Show me products from Rajasthan. -> Which one is cheaper? -> Tell me more about it."""
    rajasthan_products = product_catalog.filter_products(region="Rajasthan", limit=20)
    turn1_ids = [p["product_id"] for p in rajasthan_products]
    cheapest = min(rajasthan_products, key=lambda p: p["price_inr"])

    turn2 = resolve_followup("Which one is cheaper?", turn1_ids)
    assert turn2.resolved_product_id == cheapest["product_id"]

    # The engine would store [turn2.resolved_product_id] as the new "last discussed" product(s).
    turn3 = resolve_followup("Tell me more about it.", [turn2.resolved_product_id])
    assert turn3.rewritten and turn3.resolved_product_id == cheapest["product_id"]
    assert cheapest["name"] in turn3.question
