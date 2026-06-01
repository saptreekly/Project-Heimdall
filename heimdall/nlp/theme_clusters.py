"""Embedding-space clustering to surface emerging narrative themes beyond static lexicons."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from heimdall.nlp.embeddings import DEFAULT_EMBEDDING_MODEL, encode_texts
from heimdall.nlp.lexicon import lexicon_hit_strength

_TOKEN_RE = re.compile(r"[a-z]{4,}")

# DBSCAN cosine distance on MiniLM unit vectors; tune for short social posts.
DBSCAN_EPS = 0.35
DBSCAN_MIN_SAMPLES = 2
EMERGING_LEXICON_MAX = 0.25
EMERGING_MIN_CLUSTER_SIZE = 3
EMERGING_MIN_COHESION = 0.55
THEME_OUTRAGE_BOOST_MAX = 0.14


@dataclass(frozen=True)
class ThemeCluster:
    cluster_id: int
    post_ids: list[int]
    size: int
    cohesion: float
    lexicon_hit_rate: float
    emerging_theme: bool
    label_terms: list[str]
    sample_text: str


@dataclass
class ThemeClusterReport:
    narrative_id: int
    post_count: int
    cluster_count: int
    method: str
    model: str
    clusters: list[ThemeCluster] = field(default_factory=list)
    post_theme_boost: dict[int, float] = field(default_factory=dict)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _label_terms(texts: list[str], *, top_n: int = 6) -> list[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(_tokenize(text))
    return [word for word, _ in counts.most_common(top_n)]


def _cluster_labels(embeddings: np.ndarray) -> tuple[np.ndarray, str]:
    n = len(embeddings)
    if n == 0:
        return np.array([], dtype=int), "none"
    if n < 3:
        return np.zeros(n, dtype=int), "single_cluster"

    try:
        from sklearn.cluster import DBSCAN, KMeans
    except ImportError as exc:
        raise RuntimeError(
            "Theme clustering requires scikit-learn: pip install -e '.[ml]'"
        ) from exc

    db = DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, metric="cosine")
    labels = db.fit_predict(embeddings)
    valid = labels[labels >= 0]
    n_clusters = len(set(valid.tolist())) if len(valid) else 0
    noise_ratio = float((labels == -1).sum()) / n

    if n_clusters >= 2 and noise_ratio <= 0.55:
        return labels, "dbscan"

    k = min(8, max(2, int(round(np.sqrt(n)))))
    labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(embeddings)
    return labels, "kmeans"


def _cluster_cohesion(embeddings: np.ndarray, member_idx: np.ndarray) -> float:
    if len(member_idx) < 2:
        return 1.0
    subset = embeddings[member_idx]
    centroid = subset.mean(axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm < 1e-9:
        return 0.0
    centroid = centroid / norm
    sims = subset @ centroid
    return float(np.clip(sims.mean(), 0.0, 1.0))


def cluster_posts(
    posts: list[tuple[int, str]],
    *,
    narrative_id: int = 0,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> ThemeClusterReport:
    """
    Cluster post texts in embedding space.

    posts: list of (post_id, text)
    """
    if not posts:
        return ThemeClusterReport(
            narrative_id=narrative_id,
            post_count=0,
            cluster_count=0,
            method="none",
            model=model_name,
        )

    post_ids = [p[0] for p in posts]
    texts = [p[1] for p in posts]
    embeddings, encoder = encode_texts(texts, model_name=model_name)
    raw_labels, method = _cluster_labels(embeddings)
    if encoder == "tfidf-fallback":
        method = f"{method}+tfidf"

    clusters: list[ThemeCluster] = []
    boosts: dict[int, float] = {}

    unique_labels = sorted({int(x) for x in raw_labels})
    for cluster_id in unique_labels:
        member_idx = np.where(raw_labels == cluster_id)[0]
        if len(member_idx) == 0:
            continue

        member_post_ids = [post_ids[i] for i in member_idx]
        member_texts = [texts[i] for i in member_idx]
        cohesion = _cluster_cohesion(embeddings, member_idx)
        lex_rates = [lexicon_hit_strength(t) for t in member_texts]
        lexicon_rate = float(np.mean(lex_rates)) if lex_rates else 0.0

        emerging = (
            len(member_idx) >= EMERGING_MIN_CLUSTER_SIZE
            and cohesion >= EMERGING_MIN_COHESION
            and lexicon_rate <= EMERGING_LEXICON_MAX
        )

        sample = max(member_texts, key=len)
        clusters.append(
            ThemeCluster(
                cluster_id=cluster_id,
                post_ids=member_post_ids,
                size=len(member_idx),
                cohesion=round(cohesion, 4),
                lexicon_hit_rate=round(lexicon_rate, 4),
                emerging_theme=emerging,
                label_terms=_label_terms(member_texts),
                sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
            )
        )

        if emerging:
            boost = min(THEME_OUTRAGE_BOOST_MAX, 0.06 + cohesion * 0.08)
            for pid in member_post_ids:
                boosts[pid] = max(boosts.get(pid, 0.0), boost)

    clusters.sort(key=lambda c: (-int(c.emerging_theme), -c.size, -c.cohesion))

    return ThemeClusterReport(
        narrative_id=narrative_id,
        post_count=len(posts),
        cluster_count=len(clusters),
        method=method,
        model=encoder,
        clusters=clusters,
        post_theme_boost=boosts,
    )


def report_to_dict(report: ThemeClusterReport) -> dict:
    return {
        "narrative_id": report.narrative_id,
        "post_count": report.post_count,
        "cluster_count": report.cluster_count,
        "method": report.method,
        "model": report.model,
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "post_ids": c.post_ids,
                "size": c.size,
                "cohesion": c.cohesion,
                "lexicon_hit_rate": c.lexicon_hit_rate,
                "emerging_theme": c.emerging_theme,
                "label_terms": c.label_terms,
                "sample_text": c.sample_text,
            }
            for c in report.clusters
        ],
        "emerging_theme_count": sum(1 for c in report.clusters if c.emerging_theme),
    }
