"""Shared embedding model loader used by ingestion and query."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=4)
def _load(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def get_model(model_name: str):
    """Return a cached SentenceTransformer for ``model_name``."""
    return _load(model_name)


def embed_texts(model_name: str, texts: list[str], batch_size: int = 32):
    model = get_model(model_name)
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
