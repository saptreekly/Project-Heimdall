"""Embedding-space clustering to surface emerging narrative themes beyond static lexicons."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field, replace

import numpy as np

from heimdall.nlp.embeddings import DEFAULT_EMBEDDING_MODEL, encode_texts
from heimdall.nlp.lexicon import lexicon_hit_strength
from heimdall.nlp.market_chatter import (
    MARKET_CLUSTER_ID,
    cluster_market_chatter_rate,
    is_market_chatter_cluster,
    is_market_chatter_post,
)
from heimdall.nlp.theme_phrases import assign_distinct_phrase_labels, label_terms as _phrase_label_terms

DBSCAN_MIN_SAMPLES = 2
EMERGING_LEXICON_MAX = 0.25
EMERGING_MIN_CLUSTER_SIZE = 3
EMERGING_MIN_COHESION = 0.55
THEME_OUTRAGE_BOOST_MAX = 0.14
MIN_TIMELINE_DISTINCTIVENESS = 0.12
MIN_CLUSTER_SIZE_EXPORT = 2
KMEANS_MAX_CLUSTERS = 6
KMEANS_POSTS_PER_CLUSTER = 25
MERGE_CENTROID_SIM = 0.87
NOISE_CLUSTER_ID = -1


@dataclass(frozen=True)
class ThemeCluster:
    cluster_id: int
    post_ids: list[int]
    size: int
    cohesion: float
    lexicon_hit_rate: float
    emerging_theme: bool
    label_terms: list[str]
    label_phrases: list[str]
    label_distinctiveness: float
    sample_text: str
    author_entropy: float = 0.0
    quality_score: float = 0.0
    is_noise: bool = False
    is_market_chatter: bool = False
    market_chatter_rate: float = 0.0
    map_x: float | None = None
    map_y: float | None = None


@dataclass
class ThemeClusterReport:
    narrative_id: int
    post_count: int
    cluster_count: int
    method: str
    model: str
    clusters: list[ThemeCluster] = field(default_factory=list)
    post_theme_boost: dict[int, float] = field(default_factory=dict)
    cluster_similarity: list[dict] = field(default_factory=list)
    merge_tree: list[dict] = field(default_factory=list)


def _label_terms(texts: list[str], *, top_n: int = 6) -> list[str]:
    return _phrase_label_terms(texts, top_n=top_n)


def _assign_distinct_cluster_labels(
    cluster_texts: dict[int, list[str]],
    all_texts: list[str],
    *,
    top_n: int = 6,
) -> dict[int, tuple[list[str], list[str], float]]:
    """Return per cluster: (display labels, fallback unigrams, distinctiveness)."""
    raw = assign_distinct_phrase_labels(cluster_texts, all_texts, top_n=top_n)
    labels: dict[int, tuple[list[str], list[str], float]] = {}
    for cluster_id, (phrases, fallback, distinctiveness) in raw.items():
        display = phrases if phrases else fallback
        labels[cluster_id] = (display, fallback, distinctiveness)
    return labels


def _author_entropy(author_ids: list[str]) -> float:
    if not author_ids:
        return 0.0
    counts = Counter(author_ids)
    n = len(author_ids)
    entropy = -sum((c / n) * math.log2(c / n) for c in counts.values() if c > 0)
    max_entropy = math.log2(len(counts)) if len(counts) > 1 else 1.0
    return round(entropy / max(max_entropy, 1e-9), 4)


def _quality_score(*, cohesion: float, distinctiveness: float, lexicon_rate: float) -> float:
    return round(0.45 * cohesion + 0.35 * distinctiveness + 0.2 * (1.0 - lexicon_rate), 4)


def _cluster_primary_label(cluster: ThemeCluster) -> str:
    if cluster.label_phrases:
        return cluster.label_phrases[0]
    if cluster.label_terms:
        return cluster.label_terms[0]
    return f"cluster {cluster.cluster_id}"


def _cluster_similarity_edges(
    centroids: dict[int, np.ndarray],
    *,
    min_sim: float = 0.35,
) -> list[dict]:
    ids = sorted(centroids.keys())
    edges: list[dict] = []
    for i, left in enumerate(ids):
        vec_left = centroids[left]
        for right in ids[i + 1 :]:
            sim = float(vec_left @ centroids[right])
            if sim >= min_sim:
                edges.append({"a": left, "b": right, "similarity": round(sim, 4)})
    edges.sort(key=lambda edge: -edge["similarity"])
    return edges


def _build_merge_tree(
    clusters: list[ThemeCluster],
    centroids: dict[int, np.ndarray],
) -> list[dict]:
    """Greedy agglomerative merge history for dendrogram visualization."""
    cluster_by_id = {c.cluster_id: c for c in clusters}
    active: dict[int, dict] = {}
    for cluster_id, centroid in centroids.items():
        cluster = cluster_by_id.get(cluster_id)
        if cluster is None or cluster.is_noise:
            continue
        active[cluster_id] = {
            "node_id": f"c{cluster_id}",
            "centroid": centroid,
            "label": _cluster_primary_label(cluster),
            "size": cluster.size,
        }

    nodes: dict[str, dict] = {
        meta["node_id"]: {
            "id": meta["node_id"],
            "cluster_id": cluster_id,
            "label": meta["label"],
            "children": [],
            "similarity": 1.0,
            "size": meta["size"],
            "leaf": True,
        }
        for cluster_id, meta in active.items()
    }

    merge_step = 0
    while len(active) >= 2:
        best_pair: tuple[int, int] | None = None
        best_sim = -1.0
        ids = list(active.keys())
        for i, left in enumerate(ids):
            vec_left = active[left]["centroid"]
            for right in ids[i + 1 :]:
                sim = float(vec_left @ active[right]["centroid"])
                if sim > best_sim:
                    best_sim = sim
                    best_pair = (left, right)
        if best_pair is None or best_sim < 0.5:
            break

        left_id, right_id = best_pair
        left_meta = active[left_id]
        right_meta = active[right_id]
        merged = left_meta["centroid"] + right_meta["centroid"]
        norm = float(np.linalg.norm(merged))
        merged_centroid = merged / norm if norm > 1e-9 else merged

        merge_id = f"m{merge_step}"
        nodes[merge_id] = {
            "id": merge_id,
            "cluster_id": None,
            "label": f"{left_meta['label']} + {right_meta['label']}",
            "children": [left_meta["node_id"], right_meta["node_id"]],
            "similarity": round(best_sim, 4),
            "size": left_meta["size"] + right_meta["size"],
            "leaf": False,
        }

        del active[left_id], active[right_id]
        active[merge_step + 100_000] = {
            "node_id": merge_id,
            "centroid": merged_centroid,
            "label": nodes[merge_id]["label"],
            "size": nodes[merge_id]["size"],
        }
        merge_step += 1

    return list(nodes.values())


def _kmeans_cluster_count(n: int) -> int:
    if n < 3:
        return 1
    return min(KMEANS_MAX_CLUSTERS, max(2, n // KMEANS_POSTS_PER_CLUSTER))


def _adaptive_dbscan_eps(embeddings: np.ndarray, *, neural: bool) -> float:
    n = len(embeddings)
    if n < 4:
        return 0.35 if neural else 0.55
    try:
        from sklearn.neighbors import NearestNeighbors
    except ImportError:
        return 0.35 if neural else 0.55

    k = min(3, n - 1)
    nn = NearestNeighbors(n_neighbors=k + 1, metric="cosine")
    nn.fit(embeddings)
    dists, _ = nn.kneighbors(embeddings)
    k_dist = np.sort(dists[:, k])
    eps = float(np.percentile(k_dist, 75))
    lo, hi = (0.22, 0.42) if neural else (0.35, 0.68)
    return float(np.clip(eps, lo, hi))


def _merge_similar_clusters(embeddings: np.ndarray, labels: np.ndarray) -> np.ndarray:
    unique = sorted({int(x) for x in labels if int(x) >= 0})
    if len(unique) < 2:
        return labels

    centroids: dict[int, np.ndarray] = {}
    for cluster_id in unique:
        idx = np.where(labels == cluster_id)[0]
        centroid = embeddings[idx].mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        centroids[cluster_id] = centroid / norm if norm > 1e-9 else centroid

    parent = {cid: cid for cid in unique}

    def find(cluster_id: int) -> int:
        while parent[cluster_id] != cluster_id:
            parent[cluster_id] = parent[parent[cluster_id]]
            cluster_id = parent[cluster_id]
        return cluster_id

    for i, left in enumerate(unique):
        for right in unique[i + 1 :]:
            sim = float(centroids[left] @ centroids[right])
            if sim >= MERGE_CENTROID_SIM:
                root_left, root_right = find(left), find(right)
                if root_left != root_right:
                    parent[root_right] = root_left

    merged = labels.copy()
    for cluster_id in unique:
        merged[labels == cluster_id] = find(cluster_id)
    return merged


def _cluster_labels(embeddings: np.ndarray, *, neural: bool) -> tuple[np.ndarray, str]:
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

    eps = _adaptive_dbscan_eps(embeddings, neural=neural)
    db = DBSCAN(eps=eps, min_samples=DBSCAN_MIN_SAMPLES, metric="cosine")
    labels = db.fit_predict(embeddings)
    labels = _merge_similar_clusters(embeddings, labels)
    valid = labels[labels >= 0]
    n_clusters = len(set(valid.tolist())) if len(valid) else 0
    noise_ratio = float((labels == -1).sum()) / n

    if n_clusters >= 2 and noise_ratio <= 0.55:
        return labels, "dbscan"

    k = _kmeans_cluster_count(n)
    labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(embeddings)
    labels = _merge_similar_clusters(embeddings, labels)
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


def _cluster_map_coords(
    cluster_ids: list[int],
    centroids: list[np.ndarray],
) -> dict[int, tuple[float, float]]:
    if len(centroids) < 2:
        return {}
    try:
        from sklearn.decomposition import PCA
    except ImportError:
        return {}

    matrix = np.vstack(centroids)
    coords = PCA(n_components=2, random_state=42).fit_transform(matrix)
    return {
        cluster_ids[i]: (round(float(coords[i, 0]), 4), round(float(coords[i, 1]), 4))
        for i in range(len(cluster_ids))
    }


def _parse_posts(
    posts: list[tuple[int, str]] | list[tuple[int, str, str | None]],
) -> tuple[list[int], list[str], list[str | None]]:
    post_ids: list[int] = []
    texts: list[str] = []
    authors: list[str | None] = []
    for row in posts:
        if len(row) == 2:
            post_ids.append(int(row[0]))
            texts.append(str(row[1]))
            authors.append(None)
        else:
            post_ids.append(int(row[0]))
            texts.append(str(row[1]))
            authors.append(str(row[2]) if row[2] is not None else None)
    return post_ids, texts, authors


def cluster_posts(
    posts: list[tuple[int, str]] | list[tuple[int, str, str | None]],
    *,
    narrative_id: int = 0,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> ThemeClusterReport:
    """
    Cluster post texts in embedding space.

    posts: list of (post_id, text) or (post_id, text, author_id)
    """
    if not posts:
        return ThemeClusterReport(
            narrative_id=narrative_id,
            post_count=0,
            cluster_count=0,
            method="none",
            model=model_name,
        )

    post_ids, texts, author_ids = _parse_posts(posts)

    narrative_idx = [i for i, text in enumerate(texts) if not is_market_chatter_post(text)]
    market_idx = [i for i, text in enumerate(texts) if is_market_chatter_post(text)]

    cluster_indices = narrative_idx if len(narrative_idx) >= 3 else list(range(len(texts)))
    cluster_texts_list = [texts[i] for i in cluster_indices]
    cluster_post_ids_list = [post_ids[i] for i in cluster_indices]
    cluster_author_ids_list = [author_ids[i] for i in cluster_indices]

    embeddings, encoder = encode_texts(cluster_texts_list, model_name=model_name)
    neural = encoder != "tfidf-fallback"
    raw_labels, method = _cluster_labels(embeddings, neural=neural)
    if encoder == "tfidf-fallback":
        method = f"{method}+tfidf"
    if market_idx and narrative_idx:
        method = f"{method}+market_filtered"

    # Map subset indices back to original post ids / texts / authors
    subset_to_global = {sub: cluster_indices[sub] for sub in range(len(cluster_indices))}
    global_post_ids = [post_ids[subset_to_global[i]] for i in range(len(cluster_indices))]
    global_texts = [texts[subset_to_global[i]] for i in range(len(cluster_indices))]
    global_author_ids = [author_ids[subset_to_global[i]] for i in range(len(cluster_indices))]

    cluster_texts: dict[int, list[str]] = {}
    unique_labels = sorted({int(x) for x in raw_labels})

    for cluster_id in unique_labels:
        member_idx = np.where(raw_labels == cluster_id)[0]
        if len(member_idx) < MIN_CLUSTER_SIZE_EXPORT:
            continue
        cluster_texts[cluster_id] = [global_texts[i] for i in member_idx]

    label_map = _assign_distinct_cluster_labels(cluster_texts, global_texts)

    centroids_for_map: list[np.ndarray] = []
    map_cluster_ids: list[int] = []
    centroids_by_id: dict[int, np.ndarray] = {}
    clusters: list[ThemeCluster] = []
    boosts: dict[int, float] = {}

    for cluster_id in unique_labels:
        member_idx = np.where(raw_labels == cluster_id)[0]
        if len(member_idx) < MIN_CLUSTER_SIZE_EXPORT:
            continue

        is_noise = cluster_id == NOISE_CLUSTER_ID
        member_post_ids = [global_post_ids[i] for i in member_idx]
        member_texts = cluster_texts[cluster_id]
        display_labels, fallback_terms, label_distinctiveness = label_map.get(
            cluster_id, ([], [], 0.0)
        )
        label_phrases = [p for p in display_labels if " " in p] or display_labels[:3]
        label_terms = display_labels if display_labels else fallback_terms
        market_rate = cluster_market_chatter_rate(member_texts)
        market_chatter = is_market_chatter_cluster(member_texts, label_terms)

        cohesion = _cluster_cohesion(embeddings, member_idx)
        lex_rates = [lexicon_hit_strength(t) for t in member_texts]
        lexicon_rate = float(np.mean(lex_rates)) if lex_rates else 0.0

        member_authors = [global_author_ids[i] for i in member_idx if global_author_ids[i]]
        author_entropy = _author_entropy(member_authors)
        quality = _quality_score(
            cohesion=cohesion,
            distinctiveness=label_distinctiveness,
            lexicon_rate=lexicon_rate,
        )
        if market_chatter:
            quality = round(quality * 0.35, 4)

        emerging = (
            not is_noise
            and not market_chatter
            and len(member_idx) >= EMERGING_MIN_CLUSTER_SIZE
            and cohesion >= EMERGING_MIN_COHESION
            and lexicon_rate <= EMERGING_LEXICON_MAX
            and label_distinctiveness >= MIN_TIMELINE_DISTINCTIVENESS
        )

        subset = embeddings[member_idx]
        centroid = subset.mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        if norm > 1e-9:
            unit = centroid / norm
            if not is_noise:
                centroids_for_map.append(unit)
                map_cluster_ids.append(cluster_id)
                centroids_by_id[cluster_id] = unit

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
                label_phrases=label_phrases,
                label_distinctiveness=label_distinctiveness,
                sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
                author_entropy=author_entropy,
                quality_score=quality,
                is_noise=is_noise,
                is_market_chatter=market_chatter,
                market_chatter_rate=market_rate,
            )
        )

        if emerging:
            boost = min(THEME_OUTRAGE_BOOST_MAX, 0.06 + cohesion * 0.08)
            for pid in member_post_ids:
                boosts[pid] = max(boosts.get(pid, 0.0), boost)

    if len(market_idx) >= MIN_CLUSTER_SIZE_EXPORT:
        market_post_ids = [post_ids[i] for i in market_idx]
        market_texts = [texts[i] for i in market_idx]
        market_authors = [author_ids[i] for i in market_idx if author_ids[i]]
        market_rate = cluster_market_chatter_rate(market_texts)
        market_labels = _phrase_label_terms(market_texts, top_n=4)
        market_phrases = [p for p in market_labels if " " in p][:2]
        sample = max(market_texts, key=len)
        clusters.append(
            ThemeCluster(
                cluster_id=MARKET_CLUSTER_ID,
                post_ids=market_post_ids,
                size=len(market_post_ids),
                cohesion=1.0,
                lexicon_hit_rate=0.0,
                emerging_theme=False,
                label_terms=market_labels[:4] or ["market chatter"],
                label_phrases=market_phrases,
                label_distinctiveness=0.0,
                sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
                author_entropy=_author_entropy([a for a in market_authors if a]),
                quality_score=0.0,
                is_noise=False,
                is_market_chatter=True,
                market_chatter_rate=market_rate,
            )
        )

    map_coords = _cluster_map_coords(map_cluster_ids, centroids_for_map)
    enriched: list[ThemeCluster] = []
    for cluster in clusters:
        x, y = map_coords.get(cluster.cluster_id, (None, None))
        enriched.append(replace(cluster, map_x=x, map_y=y))

    enriched.sort(
        key=lambda c: (
            c.is_noise,
            c.is_market_chatter,
            -c.label_distinctiveness,
            -int(c.emerging_theme),
            -c.size,
            -c.cohesion,
        )
    )

    similarity = _cluster_similarity_edges(centroids_by_id)
    merge_tree = _build_merge_tree(enriched, centroids_by_id)

    return ThemeClusterReport(
        narrative_id=narrative_id,
        post_count=len(posts),
        cluster_count=len(enriched),
        method=method,
        model=encoder,
        clusters=enriched,
        post_theme_boost=boosts,
        cluster_similarity=similarity,
        merge_tree=merge_tree,
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
                "label_phrases": c.label_phrases,
                "label_distinctiveness": c.label_distinctiveness,
                "sample_text": c.sample_text,
                "author_entropy": c.author_entropy,
                "quality_score": c.quality_score,
                "is_noise": c.is_noise,
                "is_market_chatter": c.is_market_chatter,
                "market_chatter_rate": c.market_chatter_rate,
                "map_x": c.map_x,
                "map_y": c.map_y,
            }
            for c in report.clusters
        ],
        "cluster_map": [
            {
                "cluster_id": c.cluster_id,
                "x": c.map_x,
                "y": c.map_y,
                "size": c.size,
                "label": (c.label_phrases or c.label_terms or ["?"])[0],
                "emerging_theme": c.emerging_theme,
                "is_noise": c.is_noise,
            }
            for c in report.clusters
            if c.map_x is not None and c.map_y is not None and not c.is_noise
        ],
        "emerging_theme_count": sum(1 for c in report.clusters if c.emerging_theme),
        "market_chatter_count": sum(1 for c in report.clusters if c.is_market_chatter),
        "market_chatter_post_count": sum(c.size for c in report.clusters if c.is_market_chatter),
        "distinct_theme_count": sum(
            1
            for c in report.clusters
            if c.label_distinctiveness >= MIN_TIMELINE_DISTINCTIVENESS
            and not c.is_market_chatter
            and not c.is_noise
        ),
        "cluster_similarity": report.cluster_similarity,
        "merge_candidates": [
            edge
            for edge in report.cluster_similarity
            if 0.72 <= edge["similarity"] < MERGE_CENTROID_SIM
        ],
        "merge_tree": report.merge_tree,
    }
