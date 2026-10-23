"""Typo-tolerant query correction (backend/rag/spelling.py).

Must generalise from the live catalogue vocabulary - never a hardcoded list of the professor's
four example typos - and must never "correct" a word that is already valid English/retail
phrasing or an ordinary plural of a catalogue word.
"""
from backend.rag.spelling import correct_query, reset_cache


def setup_function(_):
    reset_cache()


def test_corrects_the_four_example_typos_from_the_brief():
    cases = {
        "Banarasi silk dupata": "Dupatta",
        "Madubani painting": "Madhubani",
        "Rajashtan crafts": "Rajasthan",
        "Jaipur blue potery": "Pottery",
    }
    for question, expected_word in cases.items():
        corrected, fixes = correct_query(question)
        assert expected_word in corrected, (question, corrected)
        assert fixes, f"expected a correction for {question!r}"


def test_leaves_already_correct_text_untouched():
    text = "Tell me about the Banarasi Silk Dupatta."
    corrected, fixes = correct_query(text)
    assert corrected == text and fixes == []


def test_does_not_touch_ordinary_english_or_retail_words():
    text = "Which products are cheaper than the competitor reference price online today?"
    corrected, fixes = correct_query(text)
    assert corrected == text and fixes == []


def test_does_not_correct_a_valid_plural_of_a_catalogue_word():
    # "Textile" is a catalogue craft category; "textiles" is just its ordinary English plural,
    # not a typo, and must not be "corrected" back to the singular catalogue spelling.
    text = "Tell me about textiles from Bihar."
    corrected, fixes = correct_query(text)
    assert corrected == text and fixes == []


def test_corrects_a_technique_word_typo_not_just_product_names():
    corrected, fixes = correct_query("What technique is used for pottry in Jaipur?")
    assert "Pottery" in corrected or "pottery" in corrected.lower()
    assert any(orig.lower() == "pottry" for orig, _ in fixes)


def test_vocabulary_is_built_from_the_real_catalogue_not_a_fixed_list():
    from backend.rag.spelling import _vocabulary

    vocab = _vocabulary()
    assert "dupatta" in vocab and "rajasthan" in vocab and "madhubani" in vocab
    assert len(vocab) > 50  # the catalogue has 146 products worth of distinctive words


def test_short_words_and_region_names_are_not_mangled():
    corrected, fixes = correct_query("Show me products from Bihar under 3000 rupees.")
    assert corrected == "Show me products from Bihar under 3000 rupees." and fixes == []


def test_non_alphabetic_tokens_pass_through_untouched():
    corrected, fixes = correct_query("Show me products under ₹3,000 (id #42).")
    assert "₹3,000" in corrected and "#42" in corrected


def test_correction_feeds_a_vocabulary_word_not_a_random_near_match():
    # A short, very common English word must never be rewritten into a catalogue term just
    # because it is a few edits away from one.
    corrected, fixes = correct_query("What is the price of this item?")
    assert corrected == "What is the price of this item?" and fixes == []
