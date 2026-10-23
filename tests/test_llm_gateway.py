import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from backend.exceptions import LLMError, LLMTimeout
from backend.rag import llm as llm_module
from backend.rag.llm import LLMGateway, check_ollama


class HttpError(Exception):
    def __init__(self, status, msg="boom"):
        super().__init__(msg)
        self.status_code = status


class Scripted:
    """Fake LlamaIndex LLM: plays back a list of outcomes (exception instances or strings)."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def chat(self, messages):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(message=SimpleNamespace(content=outcome))


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(llm_module.time, "sleep", lambda s: None)


def gw(settings, outcomes):
    return LLMGateway(settings, llm=Scripted(outcomes))


def test_returns_answer(settings):
    assert gw(settings, ["  hello  "]).generate("sys", "usr") == "hello"


def test_rate_limit_is_retried_then_succeeds(settings):
    g = gw(settings, [HttpError(429), HttpError(503), "ok"])
    assert g.generate("s", "u") == "ok" and g.llm.calls == 3


def test_retries_are_bounded(make_settings):
    g = gw(make_settings(llm_max_retries=2), [HttpError(429)] * 5)
    with pytest.raises(LLMError) as exc:
        g.generate("s", "u")
    assert "429" in exc.value.message and g.llm.calls == 3


@pytest.mark.parametrize("status,needle", [(401, "API key"), (403, "API key"), (404, "not found")])
def test_auth_and_model_errors_fail_fast_with_hints(settings, status, needle):
    g = gw(settings, [HttpError(status)])
    with pytest.raises(LLMError) as exc:
        g.generate("s", "u")
    assert needle.lower() in exc.value.message.lower() and exc.value.hint and g.llm.calls == 1


def test_timeout_maps_to_504_and_is_retried_once(settings):
    g = gw(settings, [httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"), "never"])
    with pytest.raises(LLMTimeout) as exc:
        g.generate("s", "u")
    assert exc.value.http_status == 504 and g.llm.calls == 2


def test_connection_error_is_retryable(settings):
    g = gw(settings, [httpx.ConnectError("no route"), "ok"])
    assert g.generate("s", "u") == "ok"


def test_empty_answer_is_an_error_with_hint(settings):
    with pytest.raises(LLMError) as exc:
        gw(settings, ["   "]).generate("s", "u")
    assert "empty" in exc.value.message.lower() and "OLLAMA_THINK" in exc.value.hint


def test_secrets_are_not_leaked_in_error_messages(make_settings):
    from backend.logging_config import register_secret

    register_secret("sk-very-secret-token")
    g = gw(make_settings(), [ValueError("failed with key sk-very-secret-token")])
    with pytest.raises(LLMError) as exc:
        g.generate("s", "u")
    assert "sk-very-secret-token" not in exc.value.message


def test_only_one_request_runs_at_a_time(make_settings):
    s = make_settings(llm_max_concurrency=1)
    active, peak, lock = 0, 0, threading.Lock()

    class Slow:
        def chat(self, messages):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return SimpleNamespace(message=SimpleNamespace(content="ok"))

    gateways = [LLMGateway(s, llm=Slow()) for _ in range(4)]  # separate instances share the limiter
    threads = [threading.Thread(target=g.generate, args=("s", "u")) for g in gateways]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak == 1


# ---- health probe ---------------------------------------------------------------------------------
def fake_get(status=200, body=None, exc=None):
    def _get(url, headers=None, timeout=None):
        if exc:
            raise exc
        return httpx.Response(status, json=body or {}, request=httpx.Request("GET", url))
    return _get


def test_check_ollama_states(make_settings, monkeypatch):
    s = make_settings(ollama_api_key="k" * 12)
    monkeypatch.setattr(httpx, "get", fake_get(body={"models": [{"name": "gpt-oss:20b"}]}))
    assert check_ollama(s) == ("ok", None)
    monkeypatch.setattr(httpx, "get", fake_get(body={"models": [{"name": "other"}]}))
    assert check_ollama(s)[0] == "error" and "not in the list" in check_ollama(s)[1]
    monkeypatch.setattr(httpx, "get", fake_get(status=401))
    assert "rejected" in check_ollama(s)[1]
    monkeypatch.setattr(httpx, "get", fake_get(exc=httpx.ConnectError("x")))
    assert check_ollama(s)[0] == "error"
    assert check_ollama(make_settings())[0] == "not_configured"


def test_check_ollama_sends_bearer_header_without_logging_it(make_settings, monkeypatch):
    seen = {}

    def _get(url, headers=None, timeout=None):
        seen.update(headers or {})
        return httpx.Response(200, json={"models": []}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", _get)
    check_ollama(make_settings(ollama_api_key="my-token-1234"))
    assert seen["Authorization"] == "Bearer my-token-1234"
