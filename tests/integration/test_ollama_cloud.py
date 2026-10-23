"""Needs a real OLLAMA_API_KEY.  NOT run in the author's sandbox (no credentials, no route to ollama.com)."""
import pytest

from backend.rag.llm import LLMGateway, check_ollama


@pytest.fixture
def cloud(real_env, make_settings):
    key = real_env.get("OLLAMA_API_KEY")
    if not key:
        pytest.skip("OLLAMA_API_KEY not set")
    return make_settings(ollama_api_key=key, ollama_model=real_env.get("OLLAMA_MODEL", "gpt-oss:20b"), supabase_db_url="postgresql://u:p@h/db")


def test_key_is_accepted_and_model_exists(cloud):
    assert check_ollama(cloud) == ("ok", None)


def test_grounded_generation_round_trip(cloud):
    answer = LLMGateway(cloud).generate("Answer using only the context. Reply in one short sentence.", "Context: [1] The return window is 14 days.\n\nQuestion: How long is the return window? Cite like [1].")
    assert "14" in answer
