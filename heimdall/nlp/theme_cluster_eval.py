"""Offline metrics for theme clustering quality (golden narratives + snapshot checks)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from heimdall.nlp.theme_clusters import ThemeClusterReport


@dataclass
class ClusterEvalMetrics:
    silhouette: float | None = None
    davies_bouldin: float | None = None
    noise_ratio: float = 0.0
    narrative_purity: float | None = None
    notes: list[str] = field(default_factory=list)


def _cluster_assignments(report: ThemeClusterReport, post_ids: list[int]) -> np.ndarray:
    id_to_idx = {pid: i for i, pid in enumerate(post_ids)}
    labels = np.full(len(post_ids), -1, dtype=int)
    for cluster in report.clusters:
        if cluster.is_market_chatter or cluster.is_noise or cluster.filter_reason:
            continue
        for pid in cluster.post_ids:
            idx = id_to_idx.get(pid)
            if idx is not None:
                labels[idx] = cluster.cluster_id
    return labels


def compute_cluster_metrics(
    embeddings: np.ndarray,
    labels: np.ndarray,
) -> tuple[float | None, float | None]:
    valid = labels >= 0
    unique = sorted({int(x) for x in labels[valid].tolist()})
    if len(unique) < 2 or valid.sum() < 4:
        return None, None
    try:
        from sklearn.metrics import davies_bouldin_score, silhouette_score
    except ImportError:
        return None, None
    subset_labels = labels[valid]
    subset_emb = embeddings[valid]
    try:
        sil = float(silhouette_score(subset_emb, subset_labels, metric="cosine"))
    except Exception:
        sil = None
    try:
        db = float(davies_bouldin_score(subset_emb, subset_labels))
    except Exception:
        db = None
    return sil, db


def evaluate_theme_report(
    report: ThemeClusterReport,
    embeddings: np.ndarray,
    post_ids: list[int],
    *,
    planted_frames: dict[str, set[int]] | None = None,
) -> ClusterEvalMetrics:
    labels = _cluster_assignments(report, post_ids)
    noise_ratio = float((labels == -1).sum()) / max(len(labels), 1)
    sil, db = compute_cluster_metrics(embeddings, labels)
    metrics = ClusterEvalMetrics(
        silhouette=round(sil, 4) if sil is not None else None,
        davies_bouldin=round(db, 4) if db is not None else None,
        noise_ratio=round(noise_ratio, 4),
    )

    if not planted_frames:
        return metrics

    id_to_cluster: dict[int, int] = {}
    for cluster in report.clusters:
        if cluster.is_market_chatter or cluster.is_noise or cluster.filter_reason:
            continue
        for pid in cluster.post_ids:
            id_to_cluster[pid] = cluster.cluster_id

    pure = 0
    total = 0
    for frame_name, frame_posts in planted_frames.items():
        clusters = [id_to_cluster[pid] for pid in frame_posts if pid in id_to_cluster]
        if not clusters:
            metrics.notes.append(f"frame '{frame_name}' not clustered")
            continue
        dominant = max(set(clusters), key=clusters.count)
        hits = sum(1 for c in clusters if c == dominant)
        purity = hits / len(clusters)
        total += 1
        if purity >= 0.67:
            pure += 1
        else:
            metrics.notes.append(f"frame '{frame_name}' purity {purity:.0%}")
    if total:
        metrics.narrative_purity = round(pure / total, 4)
    return metrics


def confidence_tier(*, model: str, quality_score: float, cohesion: float) -> str:
    neural = "tfidf" not in (model or "").lower()
    if neural and quality_score >= 0.55 and cohesion >= 0.55:
        return "high"
    if neural or quality_score >= 0.4:
        return "medium"
    return "low"
