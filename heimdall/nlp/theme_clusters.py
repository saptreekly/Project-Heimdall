"""Embedding-space clustering to surface emerging narrative themes beyond static lexicons."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from heimdall.nlp.embeddings import DEFAULT_EMBEDDING_MODEL, encode_texts
from heimdall.nlp.lexicon import lexicon_hit_strength

_TOKEN_RE = re.compile(r"[a-z]{3,}")

# Extra fillers common on social posts (sklearn ENGLISH_STOP_WORDS covers most English glue words).
_EXTRA_THEME_STOPWORDS = frozenset(
    {
        "amp",
        "com",
        "http",
        "https",
        "just",
        "like",
        "link",
        "nbsp",
        "rt",
        "via",
        "www",
    }
)

_THEME_STOPWORDS: frozenset[str] | None = None

# DBSCAN cosine distance on MiniLM unit vectors; tune for short social posts.
DBSCAN_EPS = 0.35
DBSCAN_MIN_SAMPLES = 2
EMERGING_LEXICON_MAX = 0.25
EMERGING_MIN_CLUSTER_SIZE = 3
EMERGING_MIN_COHESION = 0.55
THEME_OUTRAGE_BOOST_MAX = 0.14
MIN_LABEL_LIFT = 1.75
MIN_TIMELINE_DISTINCTIVENESS = 0.12
MIN_CLUSTER_SIZE_EXPORT = 2
KMEANS_MAX_CLUSTERS = 6
KMEANS_POSTS_PER_CLUSTER = 25


@dataclass(frozen=True)
class ThemeCluster:
    cluster_id: int
    post_ids: list[int]
    size: int
    cohesion: float
    lexicon_hit_rate: float
    emerging_theme: bool
    label_terms: list[str]
    label_distinctiveness: float
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


def _theme_stopwords() -> frozenset[str]:
    global _THEME_STOPWORDS
    if _THEME_STOPWORDS is None:
        try:
            from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

            base = set(ENGLISH_STOP_WORDS)
        except ImportError:
            base = set()
        base.update(_EXTRA_THEME_STOPWORDS)
        _THEME_STOPWORDS = frozenset(base)
    return _THEME_STOPWORDS


def _is_meaningful_label_term(word: str) -> bool:
    w = (word or "").lower().strip()
    if len(w) < 3 or w.isdigit():
        return False
    return w not in _theme_stopwords()


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _label_terms(texts: list[str], *, top_n: int = 6) -> list[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        for word in _tokenize(text):
            if _is_meaningful_label_term(word):
                counts[word] += 1
    return [word for word, _ in counts.most_common(top_n)]


def _corpus_term_rates(all_texts: list[str]) -> dict[str, float]:
    counts: Counter[str] = Counter()
    total = 0
    for text in all_texts:
        for word in _tokenize(text):
            if _is_meaningful_label_term(word):
                counts[word] += 1
                total += 1
    if total <= 0:
        return {}
    return {word: count / total for word, count in counts.items()}


def _score_distinct_terms(
    member_texts: list[str],
    corpus_rates: dict[str, float],
) -> list[tuple[str, float]]:
    """Rank terms by lift vs the full narrative corpus (c-TF-IDF style)."""
    cluster_counts: Counter[str] = Counter()
    cluster_total = 0
    for text in member_texts:
        for word in _tokenize(text):
            if _is_meaningful_label_term(word):
                cluster_counts[word] += 1
                cluster_total += 1
    if cluster_total <= 0:
        return []

    scored: list[tuple[str, float]] = []
    for word, count in cluster_counts.items():
        cluster_rate = count / cluster_total
        corpus_rate = corpus_rates.get(word, 1.0 / max(cluster_total * 10, 1))
        lift = cluster_rate / max(corpus_rate, 1e-9)
        if lift < MIN_LABEL_LIFT:
            continue
        scored.append((word, lift * cluster_rate))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def _distinctiveness_from_scores(
    terms: list[str],
    scored: list[tuple[str, float]],
) -> float:
    if not terms:
        return 0.0
    score_map = dict(scored)
    vals = [score_map.get(term, 0.0) for term in terms[:3]]
    if not vals:
        return 0.0
    avg = sum(vals) / len(vals)
    return round(min(1.0, avg / 8.0), 4)


def _assign_distinct_cluster_labels(
    cluster_texts: dict[int, list[str]],
    all_texts: list[str],
    *,
    top_n: int = 6,
) -> dict[int, tuple[list[str], float]]:
    """Pick distinctive labels per cluster; reserve top terms for strongest clusters."""
    cluster_scores: dict[int, list[tuple[str, float]]] = {}
    for cluster_id, texts in cluster_texts.items():
        contrast = [
            line
            for other_id, other_texts in cluster_texts.items()
            if other_id != cluster_id
            for line in other_texts
        ]
        if not contrast:
            contrast = [t for t in all_texts if t not in texts] or all_texts
        cluster_scores[cluster_id] = _score_distinct_terms(texts, _corpus_term_rates(contrast))
    order = sorted(
        cluster_scores.keys(),
        key=lambda cid: cluster_scores[cid][0][1] if cluster_scores[cid] else 0.0,
        reverse=True,
    )

    claimed: set[str] = set()
    labels: dict[int, tuple[list[str], float]] = {}
    for cluster_id in order:
        scored = cluster_scores[cluster_id]
        terms: list[str] = []
        for word, _ in scored:
            if word in claimed:
                continue
            terms.append(word)
            claimed.add(word)
            if len(terms) >= top_n:
                break
        if len(terms) < min(3, top_n):
            for word, _ in scored:
                if word not in terms:
                    terms.append(word)
                if len(terms) >= top_n:
                    break
        if len(terms) < min(2, top_n):
            terms = _label_terms(cluster_texts[cluster_id], top_n=top_n)
        distinctiveness = _distinctiveness_from_scores(terms, scored)
        labels[cluster_id] = (terms[:top_n], distinctiveness)
    return labels


def _kmeans_cluster_count(n: int) -> int:
    """Fewer, broader clusters — avoids 14 near-duplicate KMeans slices on ~200 posts."""
    if n < 3:
        return 1
    return min(KMEANS_MAX_CLUSTERS, max(2, n // KMEANS_POSTS_PER_CLUSTER))


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

    k = _kmeans_cluster_count(n)
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
    cluster_texts: dict[int, list[str]] = {}

    unique_labels = sorted({int(x) for x in raw_labels if int(x) >= 0})
    for cluster_id in unique_labels:
        member_idx = np.where(raw_labels == cluster_id)[0]
        if len(member_idx) < MIN_CLUSTER_SIZE_EXPORT:
            continue

        member_post_ids = [post_ids[i] for i in member_idx]
        member_texts = [texts[i] for i in member_idx]
        cluster_texts[cluster_id] = member_texts

    label_map = _assign_distinct_cluster_labels(cluster_texts, texts)

    for cluster_id in unique_labels:
        member_idx = np.where(raw_labels == cluster_id)[0]
        if len(member_idx) < MIN_CLUSTER_SIZE_EXPORT:
            continue

        member_post_ids = [post_ids[i] for i in member_idx]
        member_texts = cluster_texts[cluster_id]
        label_terms, label_distinctiveness = label_map.get(cluster_id, ([], 0.0))
        cohesion = _cluster_cohesion(embeddings, member_idx)
        lex_rates = [lexicon_hit_strength(t) for t in member_texts]
        lexicon_rate = float(np.mean(lex_rates)) if lex_rates else 0.0

        emerging = (
            len(member_idx) >= EMERGING_MIN_CLUSTER_SIZE
            and cohesion >= EMERGING_MIN_COHESION
            and lexicon_rate <= EMERGING_LEXICON_MAX
            and label_distinctiveness >= MIN_TIMELINE_DISTINCTIVENESS
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
                label_terms=label_terms,
                label_distinctiveness=label_distinctiveness,
                sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
            )
        )

        if emerging:
            boost = min(THEME_OUTRAGE_BOOST_MAX, 0.06 + cohesion * 0.08)
            for pid in member_post_ids:
                boosts[pid] = max(boosts.get(pid, 0.0), boost)

    clusters.sort(
        key=lambda c: (-c.label_distinctiveness, -int(c.emerging_theme), -c.size, -c.cohesion)
    )

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
                "label_distinctiveness": c.label_distinctiveness,
                "sample_text": c.sample_text,
            }
            for c in report.clusters
        ],
        "emerging_theme_count": sum(1 for c in report.clusters if c.emerging_theme),
        "distinct_theme_count": sum(
            1 for c in report.clusters if c.label_distinctiveness >= MIN_TIMELINE_DISTINCTIVENESS
        ),
    }
