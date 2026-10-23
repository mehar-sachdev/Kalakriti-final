"""Integration tests need real services and are skipped unless configured.

    TEST_DATABASE_URL=postgresql://user:pw@host:5432/db   (any Postgres with pgvector; a scratch schema is used)
    OLLAMA_API_KEY=...                                    (only for the Ollama Cloud test)
"""
import pytest

from tests.conftest import ORIGINAL_ENV


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def real_env():
    return ORIGINAL_ENV
