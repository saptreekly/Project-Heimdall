"""Embedding-space clustering to surface emerging narrative themes beyond static lexicons."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime

import numpy as np

from heimdall.nlp.embeddings import DEFAULT_EMBEDDING_MODEL
from heimdall.nlp.lexicon import lexicon_hit_strength
from heimdall.nlp.market_chatter import (
    MARKET_CLUSTER_ID,
    cluster_market_chatter_rate,
    is_market_chatter_cluster,
)
from heimdall.nlp.post_embeddings import resolve_embedding_matrix
from heimdall.nlp.theme_phrases import assign_distinct_phrase_labels, label_terms as _phrase_label_terms
from heimdall.nlp.theme_prefilter import (
    NON_ENGLISH_CLUSTER_ID,
    OFF_TOPIC_CLUSTER_ID,
    PROMO_CLUSTER_ID,
    SHORT_CLUSTER_ID,
    PrefilterReason,
    classify_post_for_clustering,
    narrative_keyword_hits,
    prefilter_cluster_id,
)

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
TWO_PASS_MIN_SIZE = 8
LINEAGE_OVERLAP_MIN = 0.35

FILTER_BUCKET_META: dict[int, tuple[str, str]] = {
    PROMO_CLUSTER_ID: ("promo", "Promo / link spam"),
    SHORT_CLUSTER_ID: ("short", "Ultra-short posts"),
    NON_ENGLISH_CLUSTER_ID: ("non_english", "Non-English / mixed"),
    OFF_TOPIC_CLUSTER_ID: ("off_topic", "Off-narrative keywords"),
    MARKET_CLUSTER_ID: ("market", "Market / crypto chatter"),
}


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
    confidence_tier: str = "medium"
    is_noise: bool = False
    is_market_chatter: bool = False
    market_chatter_rate: float = 0.0
    filter_reason: str | None = None
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
    quality_metrics: dict = field(default_factory=dict)
    theme_lineage: list[dict] = field(default_factory=list)
    filtered_post_count: int = 0


def _label_terms(texts: list[str], *, top_n: int = 6) -> list[str]:
    return _phrase_label_terms(texts, top_n=top_n)


def _assign_distinct_cluster_labels(
    cluster_texts: dict[int, list[str]],
    all_texts: list[str],
    *,
    top_n: int = 6,
) -> dict[int, tuple[list[str], list[str], float]]:
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


def _confidence_tier(*, model: str, quality_score: float, cohesion: float) -> str:
    neural = "tfidf" not in (model or "").lower()
    if neural and quality_score >= 0.55 and cohesion >= 0.55:
        return "high"
    if neural or quality_score >= 0.4:
        return "medium"
    return "low"


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
    cluster_by_id = {c.cluster_id: c for c in clusters}
    active: dict[int, dict] = {}
    for cluster_id, centroid in centroids.items():
        cluster = cluster_by_id.get(cluster_id)
        if cluster is None or cluster.is_noise or cluster.filter_reason:
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


def _apply_must_link_groups(
    labels: np.ndarray,
    must_link_groups: list[list[int]] | None,
    post_ids: list[int],
) -> np.ndarray:
    if not must_link_groups:
        return labels
    id_to_idx = {pid: i for i, pid in enumerate(post_ids)}
    merged = labels.copy()
    for group in must_link_groups:
        indices = [id_to_idx[pid] for pid in group if pid in id_to_idx]
        if len(indices) < 2:
            continue
        cluster_ids = [int(merged[i]) for i in indices if merged[i] >= 0]
        if cluster_ids:
            target = Counter(cluster_ids).most_common(1)[0][0]
        else:
            target = max(labels) + 1 if len(labels) else 0
        for idx in indices:
            merged[idx] = target
    return merged


def _hdbscan_labels(embeddings: np.ndarray) -> tuple[np.ndarray, str] | None:
    n = len(embeddings)
    if n < 4:
        return None
    try:
        import hdbscan
    except ImportError:
        return None

    min_cluster_size = max(3, min(5, n // 12 or 3))
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=DBSCAN_MIN_SAMPLES,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(embeddings)
    valid = labels[labels >= 0]
    n_clusters = len(set(valid.tolist())) if len(valid) else 0
    noise_ratio = float((labels == -1).sum()) / n
    if n_clusters >= 2 and noise_ratio <= 0.65:
        return labels, "hdbscan"
    if n_clusters >= 1 and noise_ratio <= 0.45:
        return labels, "hdbscan"
    return None


def _dbscan_labels(embeddings: np.ndarray, *, neural: bool) -> tuple[np.ndarray, str]:
    from sklearn.cluster import DBSCAN

    eps = _adaptive_dbscan_eps(embeddings, neural=neural)
    db = DBSCAN(eps=eps, min_samples=DBSCAN_MIN_SAMPLES, metric="cosine")
    labels = db.fit_predict(embeddings)
    return labels, "dbscan"


def _kmeans_labels(embeddings: np.ndarray) -> tuple[np.ndarray, str]:
    from sklearn.cluster import KMeans

    k = _kmeans_cluster_count(len(embeddings))
    labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(embeddings)
    return labels, "kmeans"


def _two_pass_refinement(embeddings: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Re-cluster large super-clusters for finer narrative frames."""
    refined = labels.copy()
    next_id = int(labels.max()) + 1 if len(labels) else 0
    for cluster_id in sorted({int(x) for x in labels if int(x) >= 0}):
        member_idx = np.where(labels == cluster_id)[0]
        if len(member_idx) < TWO_PASS_MIN_SIZE:
            continue
        subset = embeddings[member_idx]
        inner = _hdbscan_labels(subset)
        if inner is None:
            inner_labels, _ = _dbscan_labels(subset, neural=True)
        else:
            inner_labels, _ = inner
        inner_valid = inner_labels[inner_labels >= 0]
        if len(set(inner_valid.tolist())) < 2:
            continue
        mapping: dict[int, int] = {}
        for inner_id in sorted({int(x) for x in inner_labels if int(x) >= 0}):
            mapping[inner_id] = cluster_id if inner_id == 0 else next_id
            if inner_id != 0:
                next_id += 1
        for local_i, global_i in enumerate(member_idx):
            inner_label = int(inner_labels[local_i])
            if inner_label >= 0:
                refined[global_i] = mapping.get(inner_label, cluster_id)
    return refined


def _cluster_labels(
    embeddings: np.ndarray,
    *,
    neural: bool,
    must_link_groups: list[list[int]] | None = None,
    post_ids: list[int] | None = None,
) -> tuple[np.ndarray, str]:
    n = len(embeddings)
    if n == 0:
        return np.array([], dtype=int), "none"
    if n < 3:
        return np.zeros(n, dtype=int), "single_cluster"

    try:
        from sklearn.cluster import DBSCAN, KMeans  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Theme clustering requires scikit-learn: pip install -e '.[ml]'"
        ) from exc

    method = "hdbscan"
    hdb = _hdbscan_labels(embeddings)
    if hdb is not None:
        labels, method = hdb
    else:
        labels, method = _dbscan_labels(embeddings, neural=neural)
        valid = labels[labels >= 0]
        n_clusters = len(set(valid.tolist())) if len(valid) else 0
        noise_ratio = float((labels == -1).sum()) / n
        if n_clusters < 2 or noise_ratio > 0.55:
            labels, method = _kmeans_labels(embeddings)

    labels = _merge_similar_clusters(embeddings, labels)
    labels = _two_pass_refinement(embeddings, labels)
    if post_ids:
        labels = _apply_must_link_groups(labels, must_link_groups, post_ids)
        labels = _merge_similar_clusters(embeddings, labels)
    return labels, method


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


def _iso_week(day: str) -> str:
    try:
        dt = datetime.fromisoformat(day.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.strptime(day[:10], "%Y-%m-%d")
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _cluster_label_key(cluster: dict) -> str:
    phrases = cluster.get("label_phrases") or []
    if phrases:
        return phrases[0]
    terms = cluster.get("label_terms") or []
    if terms:
        return terms[0]
    return f"cluster-{cluster.get('cluster_id', '?')}"


def _post_overlap(a: set[int], b: set[int]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def compute_theme_lineage(
    posts: list[tuple[int, str]] | list[tuple[int, str, str | None]],
    post_dates: dict[int, str],
    *,
    narrative_id: int = 0,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    narrative_keywords: list[str] | None = None,
) -> list[dict]:
    """Weekly theme windows with lineage links across consecutive weeks."""
    post_ids, texts, authors = _parse_posts(posts)
    if not post_dates or len(post_ids) < 6:
        return []

    week_buckets: dict[str, list[int]] = defaultdict(list)
    for i, pid in enumerate(post_ids):
        day = post_dates.get(pid)
        if not day:
            continue
        week_buckets[_iso_week(day)].append(i)

    weeks = sorted(week_buckets.keys())
    if len(weeks) < 2:
        return []

    week_reports: dict[str, dict] = {}
    for week in weeks:
        indices = week_buckets[week]
        subset_posts = [
            (post_ids[i], texts[i], authors[i]) if authors[i] is not None else (post_ids[i], texts[i])
            for i in indices
        ]
        if len(subset_posts) < 3:
            continue
        report = cluster_posts(
            subset_posts,
            narrative_id=narrative_id,
            model_name=model_name,
            narrative_keywords=narrative_keywords,
        )
        week_reports[week] = report_to_dict(report)

    lineage: list[dict] = []
    prev_week: str | None = None
    for week in weeks:
        data = week_reports.get(week)
        if not data:
            continue
        narrative_clusters = [
            c
            for c in data.get("clusters", [])
            if not c.get("is_market_chatter")
            and not c.get("is_noise")
            and not c.get("filter_reason")
        ]
        entry = {
            "week": week,
            "cluster_count": len(narrative_clusters),
            "clusters": [
                {
                    "cluster_id": c["cluster_id"],
                    "label": _cluster_label_key(c),
                    "size": c["size"],
                    "post_ids": c["post_ids"],
                    "emerging_theme": c.get("emerging_theme", False),
                }
                for c in narrative_clusters
            ],
            "continues_from": [],
        }
        if prev_week and prev_week in week_reports:
            prev_clusters = [
                c
                for c in week_reports[prev_week].get("clusters", [])
                if not c.get("is_market_chatter")
                and not c.get("is_noise")
                and not c.get("filter_reason")
            ]
            for cluster in entry["clusters"]:
                current_posts = set(cluster["post_ids"])
                for prev in prev_clusters:
                    overlap = _post_overlap(current_posts, set(prev["post_ids"]))
                    if overlap >= LINEAGE_OVERLAP_MIN:
                        entry["continues_from"].append(
                            {
                                "week": prev_week,
                                "label": _cluster_label_key(prev),
                                "overlap": round(overlap, 4),
                            }
                        )
        lineage.append(entry)
        prev_week = week
    return lineage


def _build_filter_bucket_cluster(
    cluster_id: int,
    post_ids: list[int],
    texts: list[str],
    authors: list[str | None],
    *,
    filter_reason: str,
    default_label: str,
) -> ThemeCluster:
    labels = _phrase_label_terms(texts, top_n=4) or [default_label]
    sample = max(texts, key=len)
    member_authors = [a for a in authors if a]
    return ThemeCluster(
        cluster_id=cluster_id,
        post_ids=post_ids,
        size=len(post_ids),
        cohesion=1.0,
        lexicon_hit_rate=0.0,
        emerging_theme=False,
        label_terms=labels[:4],
        label_phrases=[p for p in labels if " " in p][:2],
        label_distinctiveness=0.0,
        sample_text=sample[:240] + ("…" if len(sample) > 240 else ""),
        author_entropy=_author_entropy(member_authors),
        quality_score=0.0,
        confidence_tier="low",
        is_noise=False,
        is_market_chatter=filter_reason == "market",
        market_chatter_rate=cluster_market_chatter_rate(texts) if filter_reason == "market" else 0.0,
        filter_reason=filter_reason,
    )


def cluster_posts(
    posts: list[tuple[int, str]] | list[tuple[int, str, str | None]],
    *,
    narrative_id: int = 0,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    cached_embeddings: dict[int, np.ndarray] | None = None,
    must_link_groups: list[list[int]] | None = None,
    narrative_keywords: list[str] | None = None,
    post_dates: dict[int, str] | None = None,
) -> ThemeClusterReport:
    if not posts:
        return ThemeClusterReport(
            narrative_id=narrative_id,
            post_count=0,
            cluster_count=0,
            method="none",
            model=model_name,
        )

    post_ids, texts, author_ids = _parse_posts(posts)

    apply_off_topic = False
    if narrative_keywords:
        hits = sum(1 for text in texts if narrative_keyword_hits(text, narrative_keywords) >= 1)
        apply_off_topic = hits / max(len(texts), 1) >= 0.25

    bucket_indices: dict[int, list[int]] = defaultdict(list)
    narrative_idx: list[int] = []
    for i, text in enumerate(texts):
        reason = classify_post_for_clustering(text, narrative_keywords=narrative_keywords)
        if reason == PrefilterReason.OFF_TOPIC and not apply_off_topic:
            reason = PrefilterReason.NARRATIVE
        if reason == PrefilterReason.NARRATIVE:
            narrative_idx.append(i)
            continue
        if reason == PrefilterReason.MARKET:
            bucket_indices[MARKET_CLUSTER_ID].append(i)
            continue
        bucket_id = prefilter_cluster_id(reason)
        if bucket_id is not None:
            bucket_indices[bucket_id].append(i)

    cluster_indices = narrative_idx if len(narrative_idx) >= 3 else list(range(len(texts)))
    cluster_texts_list = [texts[i] for i in cluster_indices]
    cluster_post_ids_list = [post_ids[i] for i in cluster_indices]

    embeddings, encoder = resolve_embedding_matrix(
        cluster_post_ids_list,
        cluster_texts_list,
        cached=cached_embeddings,
        model_name=model_name,
    )
    neural = encoder != "tfidf-fallback"
    raw_labels, method = _cluster_labels(
        embeddings,
        neural=neural,
        must_link_groups=must_link_groups,
        post_ids=cluster_post_ids_list,
    )
    if encoder == "tfidf-fallback":
        method = f"{method}+tfidf"
    if bucket_indices:
        method = f"{method}+prefiltered"
    if must_link_groups:
        method = f"{method}+must_link"

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

        tier = _confidence_tier(model=encoder, quality_score=quality, cohesion=cohesion)

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
                confidence_tier=tier,
                is_noise=is_noise,
                is_market_chatter=market_chatter,
                market_chatter_rate=market_rate,
            )
        )

        if emerging:
            boost = min(THEME_OUTRAGE_BOOST_MAX, 0.06 + cohesion * 0.08)
            for pid in member_post_ids:
                boosts[pid] = max(boosts.get(pid, 0.0), boost)

    filtered_count = 0
    for bucket_id, indices in bucket_indices.items():
        if len(indices) < MIN_CLUSTER_SIZE_EXPORT:
            continue
        reason, default_label = FILTER_BUCKET_META.get(bucket_id, ("filtered", "Filtered posts"))
        bucket_post_ids = [post_ids[i] for i in indices]
        bucket_texts = [texts[i] for i in indices]
        bucket_authors = [author_ids[i] for i in indices]
        clusters.append(
            _build_filter_bucket_cluster(
                bucket_id,
                bucket_post_ids,
                bucket_texts,
                bucket_authors,
                filter_reason=reason,
                default_label=default_label,
            )
        )
        filtered_count += len(indices)

    map_coords = _cluster_map_coords(map_cluster_ids, centroids_for_map)
    enriched: list[ThemeCluster] = []
    for cluster in clusters:
        x, y = map_coords.get(cluster.cluster_id, (None, None))
        enriched.append(replace(cluster, map_x=x, map_y=y))

    enriched.sort(
        key=lambda c: (
            c.is_noise,
            c.filter_reason is not None,
            c.is_market_chatter,
            -c.label_distinctiveness,
            -int(c.emerging_theme),
            -c.size,
            -c.cohesion,
        )
    )

    similarity = _cluster_similarity_edges(centroids_by_id)
    merge_tree = _build_merge_tree(enriched, centroids_by_id)

    from heimdall.nlp.theme_cluster_eval import evaluate_theme_report

    eval_metrics = evaluate_theme_report(
        ThemeClusterReport(
            narrative_id=narrative_id,
            post_count=len(posts),
            cluster_count=len(enriched),
            method=method,
            model=encoder,
            clusters=enriched,
        ),
        embeddings,
        cluster_post_ids_list,
    )
    quality_metrics = {
        "silhouette": eval_metrics.silhouette,
        "davies_bouldin": eval_metrics.davies_bouldin,
        "noise_ratio": eval_metrics.noise_ratio,
        "narrative_purity": eval_metrics.narrative_purity,
        "notes": eval_metrics.notes,
    }

    theme_lineage: list[dict] = []
    if post_dates:
        theme_lineage = compute_theme_lineage(
            posts,
            post_dates,
            narrative_id=narrative_id,
            model_name=model_name,
            narrative_keywords=narrative_keywords,
        )

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
        quality_metrics=quality_metrics,
        theme_lineage=theme_lineage,
        filtered_post_count=filtered_count,
    )


def report_to_dict(report: ThemeClusterReport) -> dict:
    return {
        "narrative_id": report.narrative_id,
        "post_count": report.post_count,
        "cluster_count": report.cluster_count,
        "method": report.method,
        "model": report.model,
        "filtered_post_count": report.filtered_post_count,
        "quality_metrics": report.quality_metrics,
        "theme_lineage": report.theme_lineage,
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
                "confidence_tier": c.confidence_tier,
                "is_noise": c.is_noise,
                "is_market_chatter": c.is_market_chatter,
                "market_chatter_rate": c.market_chatter_rate,
                "filter_reason": c.filter_reason,
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
            if c.map_x is not None and c.map_y is not None and not c.is_noise and not c.filter_reason
        ],
        "emerging_theme_count": sum(1 for c in report.clusters if c.emerging_theme),
        "market_chatter_count": sum(1 for c in report.clusters if c.is_market_chatter),
        "market_chatter_post_count": sum(
            c.size for c in report.clusters if c.is_market_chatter or c.filter_reason == "market"
        ),
        "distinct_theme_count": sum(
            1
            for c in report.clusters
            if c.label_distinctiveness >= MIN_TIMELINE_DISTINCTIVENESS
            and not c.is_market_chatter
            and not c.is_noise
            and not c.filter_reason
        ),
        "cluster_similarity": report.cluster_similarity,
        "merge_candidates": [
            edge
            for edge in report.cluster_similarity
            if 0.72 <= edge["similarity"] < MERGE_CENTROID_SIM
        ],
        "merge_tree": report.merge_tree,
    }
