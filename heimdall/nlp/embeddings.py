"""Lazy-loaded sentence embeddings (requires pip install -e '.[ml]')."""

from __future__ import annotations

import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_model = None
_model_name: str | None = None


class EmbeddingUnavailableError(RuntimeError):
    pass


def neural_embeddings_enabled() -> bool:
    """When false, use TF-IDF only (avoids Hugging Face hub rate limits in CI)."""
    return os.environ.get("USE_NEURAL_EMBEDDINGS", "true").lower() not in ("0", "false", "no")


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


def encode_texts_tfidf(texts: list[str], *, max_features: int = 384) -> np.ndarray:
    """Lexical fallback when sentence-transformers/torch are unavailable (e.g. Python 3.14)."""
    if not texts:
        return np.zeros((0, max_features), dtype=np.float32)
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize
    except ImportError as exc:
        raise EmbeddingUnavailableError(
            "TF-IDF fallback requires scikit-learn: pip install -e '.[ml]'"
        ) from exc

    cleaned = [(t or "").strip()[:512] or " " for t in texts]
    matrix = TfidfVectorizer(
        max_features=max_features,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    ).fit_transform(cleaned)
    dense = matrix.toarray().astype(np.float32)
    return np.asarray(normalize(dense, norm="l2"), dtype=np.float32)


def encode_texts(
    texts: list[str],
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 32,
    allow_tfidf_fallback: bool = True,
) -> tuple[np.ndarray, str]:
    """
    Return L2-normalized vectors shape (n, dim) and the encoder label used.

    Uses sentence-transformers when installed; otherwise TF-IDF if allow_tfidf_fallback.
    """
    if not texts:
        return np.zeros((0, 384), dtype=np.float32), model_name

    cleaned = [(t or "").strip()[:512] or " " for t in texts]
    if not neural_embeddings_enabled():
        return encode_texts_tfidf(cleaned), "tfidf-fallback"

    try:
        model = _load_model(model_name)
        vectors = model.encode(
            cleaned,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32), model_name
    except EmbeddingUnavailableError:
        if not allow_tfidf_fallback:
            raise
        return encode_texts_tfidf(cleaned), "tfidf-fallback"
    except Exception as exc:
        if not allow_tfidf_fallback:
            raise EmbeddingUnavailableError(str(exc)) from exc
        logger.warning("Neural embeddings unavailable (%s); using TF-IDF fallback", exc)
        return encode_texts_tfidf(cleaned), "tfidf-fallback"


def encode_texts_matrix(
    texts: list[str],
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 32,
    allow_tfidf_fallback: bool = True,
) -> np.ndarray:
    """Backward-compatible: matrix only (see encode_texts for encoder label)."""
    matrix, _ = encode_texts(
        texts,
        model_name=model_name,
        batch_size=batch_size,
        allow_tfidf_fallback=allow_tfidf_fallback,
    )
    return matrix
