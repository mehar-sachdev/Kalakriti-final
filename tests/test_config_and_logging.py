from datetime import datetime
from zoneinfo import ZoneInfo

import logging
import pytest
from pydantic import ValidationError

from backend.config import Settings
from backend.exceptions import ConfigurationError
from backend.logging_config import RedactingFilter, redact, register_secret


def test_defaults_are_safe(settings):
    assert settings.llm_max_concurrency == 1
    assert settings.enable_ingest_api is False
    assert settings.app_api_key is None
    assert settings.resolved_embedding_dim == 384  # hash provider


def test_known_model_dimension_and_signature(make_settings):
    s = make_settings(embedding_provider="huggingface", embedding_model="BAAI/bge-small-en-v1.5")
    assert s.resolved_embedding_dim == 384
    assert s.embedding_signature == "huggingface:BAAI/bge-small-en-v1.5:384"


def test_unknown_model_requires_explicit_dimension(make_settings):
    s = make_settings(embedding_provider="ollama", embedding_model="my-custom-model")
    with pytest.raises(ConfigurationError) as exc:
        _ = s.resolved_embedding_dim
    assert "EMBEDDING_DIM" in exc.value.hint
    assert make_settings(embedding_provider="ollama", embedding_model="my-custom-model", embedding_dim=512).resolved_embedding_dim == 512


def test_embedding_dim_settable_by_field_name_even_though_it_has_an_alias(make_settings):
    """Regression test: a field with validation_alias=AliasChoices(...) must still be settable by its
    own Python name via keyword construction (Settings(embedding_dim=512), as scripts/tests do) - this
    silently broke on pydantic-settings 2.2.x without model_config(populate_by_name=True), falling back
    to the field's default (0) with no error until resolved_embedding_dim raised a confusing message."""
    assert Settings(_env_file=None, embedding_dim=512).embedding_dim == 512
    assert make_settings(embedding_dim=512).embedding_dim == 512


def test_embedding_dim_env_var_aliases(monkeypatch):
    """Both EMBEDDING_DIM (this codebase's own name) and EMBEDDING_DIMENSION (the name used in some
    external .env templates) must set the same field."""
    monkeypatch.setenv("EMBEDDING_DIM", "768")
    assert Settings(_env_file=None).embedding_dim == 768
    monkeypatch.delenv("EMBEDDING_DIM")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")
    assert Settings(_env_file=None).embedding_dim == 1024


def test_overlap_must_be_smaller_than_chunk_size(make_settings):
    with pytest.raises(ValidationError):
        make_settings(chunk_size=100, chunk_overlap=100)


def test_require_lists_missing_settings_without_leaking_values(make_settings):
    s = make_settings()
    with pytest.raises(ConfigurationError) as exc:
        s.require("query")
    assert "SUPABASE_DB_URL" in exc.value.message and "OLLAMA_API_KEY" in exc.value.message
    ok = make_settings(supabase_db_url="postgresql://u:p@h/db", ollama_api_key="k" * 12)
    ok.require("query")  # does not raise


def test_secrets_do_not_appear_in_repr(make_settings):
    s = make_settings(ollama_api_key="super-secret-key-123", supabase_db_url="postgresql://u:hunter2pass@h/db")
    assert "super-secret-key-123" not in repr(s) and "hunter2pass" not in repr(s)


def test_env_var_aliases_from_the_assignment_spec(monkeypatch):
    """The professor's env template names APP_HOST/APP_PORT/EMBEDDING_DIMENSION; our own code
    (and tests) use API_HOST/API_PORT/EMBEDDING_DIM. Both must work."""
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_PORT", "9999")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "768")
    s = Settings(_env_file=None)
    assert (s.api_host, s.api_port, s.embedding_dim) == ("0.0.0.0", 9999, 768)


def test_local_ollama_needs_no_key(make_settings):
    s = make_settings(supabase_db_url="postgresql://u:p@h/db", ollama_base_url="http://localhost:11434")
    assert s.missing_for("query") == []


@pytest.mark.parametrize("value,expected", [("", None), ("low", "low"), ("true", True), ("false", False)])
def test_think_parsing(make_settings, value, expected):
    assert make_settings(ollama_think=value).ollama_think_value == expected


def test_think_rejects_garbage(make_settings):
    with pytest.raises(ConfigurationError):
        _ = make_settings(ollama_think="banana").ollama_think_value


def test_off_peak_disabled_is_always_true(settings):
    assert settings.is_off_peak() is True


@pytest.mark.parametrize("hour,inside", [(23, True), (2, True), (6, True), (7, False), (12, False), (21, False), (22, True)])
def test_off_peak_window_wrapping_midnight(make_settings, hour, inside):
    s = make_settings(offpeak_enabled=True, offpeak_start="22:00", offpeak_end="07:00", offpeak_tz="Asia/Kolkata")
    now = datetime(2026, 9, 20, hour, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert s.is_off_peak(now) is inside


def test_off_peak_same_day_window_and_timezone_conversion(make_settings):
    s = make_settings(offpeak_enabled=True, offpeak_start="01:00", offpeak_end="05:00", offpeak_tz="Asia/Kolkata")
    utc_time = datetime(2026, 9, 19, 21, 0, tzinfo=ZoneInfo("UTC"))  # = 02:30 IST next day
    assert s.is_off_peak(utc_time) is True


def test_invalid_off_peak_time_is_reported(make_settings):
    s = make_settings(offpeak_enabled=True, offpeak_start="25:99x")
    with pytest.raises(ConfigurationError):
        s.is_off_peak()


# ---- redaction ---------------------------------------------------------------------------
def test_redacts_password_in_connection_url():
    out = redact("connecting to postgresql://postgres.abc:MyS3cretPw@aws-0.pooler.supabase.com:5432/postgres")
    assert "MyS3cretPw" not in out and "postgres.abc" in out


def test_redacts_bearer_and_key_assignments():
    assert "abcdef123456" not in redact("Authorization: Bearer abcdef123456789")
    assert "zzzzzzzzzz" not in redact("OLLAMA_API_KEY=zzzzzzzzzz")


def test_redacts_registered_literal_secret():
    register_secret("literal-secret-value")
    assert "literal-secret-value" not in redact("oops literal-secret-value leaked")


def test_logging_filter_redacts_args_and_exceptions(caplog):
    register_secret("topsecret99")
    logger = logging.getLogger("t.redact")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="t.redact"):
        try:
            raise RuntimeError("bad topsecret99")
        except RuntimeError:
            logger.exception("failed with %s", "topsecret99")
    handler_text = "\n".join(r.getMessage() + (r.exc_text or "") for r in caplog.records)
    assert "topsecret99" not in handler_text


def test_settings_register_secrets_for_redaction(make_settings):
    s = make_settings(supabase_db_url="postgresql://u:pw-very-secret@h/db", ollama_api_key="key-very-secret")
    s.register_secrets_for_redaction()
    assert "pw-very-secret" not in redact("x pw-very-secret y") and "key-very-secret" not in redact("key-very-secret")
