"""Near-duplicate text detection for copypasta / coordinated messaging."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class DuplicateCluster:
    normalized_text: str
    post_ids: list[int]
    author_ids: list[str]
    count: int
    sample_text: str


def normalize_text(text: str, *, max_len: int = 280) -> str:
    lowered = (text or "").lower()
    lowered = _WS_RE.sub(" ", lowered).strip()
    return lowered[:max_len]


def find_duplicate_text_clusters(
    posts: pd.DataFrame,
    *,
    min_posts: int = 2,
    text_col: str = "text",
    post_id_col: str = "post_id",
    author_col: str = "author_id",
) -> list[DuplicateCluster]:
    if posts.empty or text_col not in posts.columns:
        return []

    working = posts[[post_id_col, author_col, text_col]].copy()
    working["_norm"] = working[text_col].map(lambda t: normalize_text(str(t)))

    clusters: list[DuplicateCluster] = []
    for norm, group in working.groupby("_norm"):
        if not norm or len(group) < min_posts:
            continue
        sample = str(group.iloc[0][text_col])
        clusters.append(
            DuplicateCluster(
                normalized_text=norm,
                post_ids=[int(x) for x in group[post_id_col].tolist()],
                author_ids=sorted({str(x) for x in group[author_col].tolist()}),
                count=len(group),
                sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
            )
        )

    clusters.sort(key=lambda c: (-c.count, -len(c.author_ids)))
    return clusters
