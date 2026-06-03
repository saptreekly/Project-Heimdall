"""Persist and load L2-normalized post embedding vectors."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.db.models import PostEmbedding
from heimdall.nlp.embeddings import DEFAULT_EMBEDDING_MODEL, encode_texts

logger = logging.getLogger(__name__)

EMBEDDING_DTYPE = np.float32


def vector_to_blob(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=EMBEDDING_DTYPE).tobytes()


def blob_to_vector(blob: bytes, *, dim: int | None = None) -> np.ndarray:
    arr = np.frombuffer(blob, dtype=EMBEDDING_DTYPE)
    if dim is not None and arr.size != dim:
        raise ValueError(f"expected {dim} floats, got {arr.size}")
    return arr.copy()


def encode_single_text(text: str, *, model_name: str = DEFAULT_EMBEDDING_MODEL) -> tuple[np.ndarray, str]:
    matrix, encoder = encode_texts([text], model_name=model_name)
    if matrix.size == 0:
        return np.zeros(384, dtype=EMBEDDING_DTYPE), encoder
    return matrix[0], encoder


async def load_post_embeddings(
    session: AsyncSession,
    post_ids: list[int],
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> dict[int, np.ndarray]:
    if not post_ids:
        return {}
    result = await session.execute(
        select(PostEmbedding).where(
            PostEmbedding.post_id.in_(post_ids),
            PostEmbedding.model == model_name,
        )
    )
    loaded: dict[int, np.ndarray] = {}
    for row in result.scalars().all():
        loaded[row.post_id] = blob_to_vector(row.vector, dim=row.dim)
    return loaded


async def persist_post_embedding(
    session: AsyncSession,
    post_id: int,
    text: str,
    *,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> str:
    vector, encoder = encode_single_text(text, model_name=model_name)
    dim = int(vector.shape[0])
    blob = vector_to_blob(vector)
    existing = await session.get(PostEmbedding, post_id)
    now = datetime.now(timezone.utc)
    if existing is None:
        session.add(
            PostEmbedding(
                post_id=post_id,
                model=encoder,
                dim=dim,
                vector=blob,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        existing.model = encoder
        existing.dim = dim
        existing.vector = blob
        existing.updated_at = now
    return encoder


def resolve_embedding_matrix(
    post_ids: list[int],
    texts: list[str],
    *,
    cached: dict[int, np.ndarray] | None,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> tuple[np.ndarray, str]:
    """Build embedding matrix, re-encoding only missing or stale rows."""
    cached = cached or {}
    if all(pid in cached for pid in post_ids) and cached:
        encoder = model_name
        rows = [cached[pid] for pid in post_ids]
        return np.vstack(rows).astype(EMBEDDING_DTYPE), encoder

    missing_idx = [i for i, pid in enumerate(post_ids) if pid not in cached]
    if not missing_idx:
        rows = [cached[pid] for pid in post_ids]
        return np.vstack(rows).astype(EMBEDDING_DTYPE), model_name

    missing_texts = [texts[i] for i in missing_idx]
    fresh, encoder = encode_texts(missing_texts, model_name=model_name)
    rows: list[np.ndarray] = []
    fresh_i = 0
    for i, pid in enumerate(post_ids):
        if pid in cached:
            rows.append(cached[pid])
        else:
            rows.append(fresh[fresh_i])
            fresh_i += 1
    return np.vstack(rows).astype(EMBEDDING_DTYPE), encoder
