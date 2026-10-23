"""Embedding model factory.

Ollama Cloud offers no embedding models (checked against https://ollama.com/api/tags),
so embeddings are computed locally and for free:

* ``huggingface`` (default) - sentence-transformers model, e.g. BAAI/bge-small-en-v1.5;
* ``ollama``                - a *local* Ollama daemon (`ollama pull nomic-embed-text`);
* ``hash``                  - deterministic lexical hashing, **for tests/CI only**.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re

from llama_index.core.base.embeddings.base import BaseEmbedding

from backend.config import Settings
from backend.exceptions import ConfigurationError

logger = logging.getLogger(__name__)
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class DeterministicHashEmbedding(BaseEmbedding):
    """Signed feature hashing of word tokens.  NOT semantic - lexical overlap only.

    Exists so the whole pipeline (chunking, storage, filters, retrieval, API) can be
    tested without downloading a model.  Never use it for real retrieval quality claims.
    """

    dim: int = 384

    def __init__(self, dim: int = 384, **kwargs):
        super().__init__(model_name="deterministic-hash", embed_batch_size=64, dim=dim, **kwargs)

    @classmethod
    def class_name(cls) -> str:
        return "DeterministicHashEmbedding"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _TOKEN_RE.findall(text.lower()):
            digest = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            vec[digest % self.dim] += 1.0 if (digest >> 64) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._vector(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._vector(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._vector(text)


def get_embed_model(settings: Settings) -> BaseEmbedding:
    provider = settings.embedding_provider
    if provider == "hash":
        logger.warning("Using the deterministic HASH embedding model: for tests only, retrieval is lexical, not semantic.")
        return DeterministicHashEmbedding(dim=settings.resolved_embedding_dim)

    if provider == "huggingface":
        try:
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        except ImportError as exc:
            raise ConfigurationError(
                "The HuggingFace embedding integration is not installed.",
                hint="pip install llama-index-embeddings-huggingface",
            ) from exc
        kwargs = {}
        if settings.embedding_query_instruction and "bge" in settings.embedding_model.lower():
            kwargs["query_instruction"] = settings.embedding_query_instruction
        logger.info("Loading embedding model %s (first run downloads it from Hugging Face)", settings.embedding_model)
        return HuggingFaceEmbedding(
            model_name=settings.embedding_model,
            embed_batch_size=settings.embedding_batch_size,
            normalize=True,
            **kwargs,
        )

    if provider == "ollama":
        try:
            from llama_index.embeddings.ollama import OllamaEmbedding
        except ImportError as exc:
            raise ConfigurationError(
                "The Ollama embedding integration is not installed.", hint="pip install llama-index-embeddings-ollama"
            ) from exc
        return OllamaEmbedding(
            model_name=settings.embedding_model,
            base_url=settings.embedding_ollama_base_url,
            embed_batch_size=settings.embedding_batch_size,
        )

    raise ConfigurationError(f"Unknown EMBEDDING_PROVIDER '{provider}'.", hint="Use huggingface, ollama or hash.")
