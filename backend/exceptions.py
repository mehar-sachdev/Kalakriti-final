"""Domain exceptions.  Every one carries a stable ``code`` and a human ``hint``
so the API and CLI can print a useful, secret-free message."""
from __future__ import annotations


class RAGError(Exception):
    code = "rag_error"
    http_status = 500

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class ConfigurationError(RAGError):
    code = "configuration_error"
    http_status = 503


class DatabaseError(RAGError):
    code = "database_error"
    http_status = 503


class EmbeddingError(RAGError):
    code = "embedding_error"
    http_status = 502


class LLMError(RAGError):
    code = "llm_error"
    http_status = 502


class LLMTimeout(LLMError):
    code = "llm_timeout"
    http_status = 504


class OffPeakRestricted(RAGError):
    code = "off_peak_restricted"
    http_status = 429


class ParsingError(RAGError):
    code = "parsing_error"
    http_status = 422


class IndexingError(RAGError):
    code = "indexing_error"
    http_status = 500


class NotFoundError(RAGError):
    code = "not_found"
    http_status = 404


class InvalidRequest(RAGError):
    code = "invalid_request"
    http_status = 422


class FeatureDisabled(RAGError):
    code = "feature_disabled"
    http_status = 403
