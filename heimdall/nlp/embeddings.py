"""Lazy-loaded sentence embeddings (requires pip install -e '.[ml]')."""

from __future__ import annotations

import numpy as np

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_model = None
_model_name: str | None = None


class EmbeddingUnavailableError(RuntimeError):
    pass


def _load_model(model_name: str):
    global _model, _model_name
    if _model is not None and _model_name == model_name:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingUnavailableError(
            "Sentence embeddings require the ml extra: pip install -e '.[ml]'"
        ) from exc
    _model = SentenceTransformer(model_name)
    _model_name = model_name
    return _model


def encode_texts(
    texts: list[str],
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 32,
) -> np.ndarray:
    """Return L2-normalized embedding matrix shape (n, dim)."""
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    cleaned = [(t or "").strip()[:512] or " " for t in texts]
    model = _load_model(model_name)
    vectors = model.encode(
        cleaned,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)
