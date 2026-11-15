"""Embedding provider interface. Default = TF-IDF (no model download, zero cost). Optional = sentence-transformers
(local, free) for semantic search. Chosen via EMBEDDINGS_PROVIDER. TF-IDF needs no stored vectors."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from ..config import settings

log = logging.getLogger(__name__)
_st_model = None


def provider_name() -> str:
    if settings.embeddings_provider == "sentence-transformers" and st_available():
        return "sentence-transformers"
    return "tfidf"


def st_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except Exception:
        return False


def embed(texts: list[str]) -> Optional[np.ndarray]:
    """Return L2-normalised float32 matrix, or None when the provider needs no stored vectors."""
    if provider_name() != "sentence-transformers":
        return None
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer(settings.st_model)
    v = _st_model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return np.asarray(v, dtype="float32")
