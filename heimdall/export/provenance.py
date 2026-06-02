"""Snapshot provenance metadata for analyst trust."""

from __future__ import annotations

from heimdall.analysis.coordination_scores import graph_coverage_pct, is_graph_sufficient
from heimdall.nlp.outrage import MODEL_VERSION

SNAPSHOT_POST_LIMIT = 250
OUTRAGE_COMPRESSION_THRESHOLD = 0.15


def outrage_stats(posts: list[dict]) -> dict:
    values = [
        float(p["outrage_index"])
        for p in posts
        if p.get("outrage_index") is not None
    ]
    if not values:
        return {
            "outrage_scored_count": 0,
            "outrage_max": None,
            "outrage_mean": None,
            "outrage_compressed": False,
        }
    max_v = max(values)
    mean_v = sum(values) / len(values)
    return {
        "outrage_scored_count": len(values),
        "outrage_max": round(max_v, 4),
        "outrage_mean": round(mean_v, 4),
        "outrage_compressed": max_v <= OUTRAGE_COMPRESSION_THRESHOLD,
    }


def build_narrative_provenance(
    *,
    posts_total_db: int,
    posts_in_snapshot: list[dict],
    graph_stats: dict,
    themes: dict,
    duplicate_cluster_count: int,
    fuzzy_cluster_count: int,
) -> dict:
    stats = outrage_stats(posts_in_snapshot)
    connected = int(graph_stats.get("connected_author_count", 0))
    author_count = int(graph_stats.get("author_count", 0))
    edge_count = int(graph_stats.get("edge_count", 0))
    theme_model = str(themes.get("model") or "unknown")
    theme_method = str(themes.get("method") or "unknown")

    return {
        "posts_total_db": posts_total_db,
        "posts_in_snapshot": len(posts_in_snapshot),
        "snapshot_post_limit": SNAPSHOT_POST_LIMIT,
        "posts_truncated": posts_total_db > SNAPSHOT_POST_LIMIT,
        "posts_per_author": round(len(posts_in_snapshot) / author_count, 2) if author_count else None,
        "analysis_scope": "snapshot_cohort",
        "sentiment_scope": "snapshot_cohort",
        "text_coordination_scope": "all_db_posts",
        "outrage_model_version": MODEL_VERSION,
        "duplicate_cluster_count": duplicate_cluster_count,
        "fuzzy_cluster_count": fuzzy_cluster_count,
        "coordination_signal_count": duplicate_cluster_count + fuzzy_cluster_count,
        "distinct_theme_count": int(themes.get("distinct_theme_count") or 0),
        "theme_cluster_count": int(themes.get("cluster_count") or 0),
        "graph_edge_count": edge_count,
        "graph_author_count": author_count,
        "graph_connected_author_count": connected,
        "graph_coverage_pct": graph_coverage_pct(connected, author_count),
        "graph_sufficient": is_graph_sufficient(edge_count, connected, author_count),
        "theme_model": theme_model,
        "theme_method": theme_method,
        "theme_model_reliable": "tfidf" not in theme_model.lower(),
        **stats,
    }
