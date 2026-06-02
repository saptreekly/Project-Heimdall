"""Graph vs text coordination indices for analyst-facing export."""

from __future__ import annotations

from heimdall.analysis.duplicates import (
    DuplicateCluster,
    SYNC_BURST_SUSPICION_FLOOR,
    apply_duplicate_temporal_cib_boost,
)
from heimdall.analysis.near_duplicates import (
    CrossAuthorFuzzyCluster,
    apply_cross_author_fuzzy_cib_boost,
)

GRAPH_SUFFICIENT_MIN_EDGES = 10
GRAPH_SUFFICIENT_MIN_COVERAGE = 0.05
TWO_AUTHOR_FUZZY_FLOOR = 0.38
MULTI_AUTHOR_DUP_FLOOR = 0.32


def graph_coverage_pct(connected: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * connected / total, 1)


def is_graph_sufficient(edge_count: int, connected: int, author_count: int) -> bool:
    if edge_count < GRAPH_SUFFICIENT_MIN_EDGES or author_count <= 0:
        return False
    return (connected / author_count) >= GRAPH_SUFFICIENT_MIN_COVERAGE


def compute_text_coordination_score(
    duplicate_clusters: list[DuplicateCluster],
    fuzzy_clusters: list[CrossAuthorFuzzyCluster],
    *,
    pollination_hit_count: int = 0,
) -> float:
    """Text-level coordination index (duplicates, fuzzy Jaccard, cross-narrative)."""
    score = 0.0

    if any(c.burst_synchronized for c in duplicate_clusters):
        score = max(score, SYNC_BURST_SUSPICION_FLOOR)
    elif any(len(c.author_ids) >= 2 for c in duplicate_clusters):
        score = max(score, MULTI_AUTHOR_DUP_FLOOR)

    if any(c.burst_synchronized for c in fuzzy_clusters):
        score = max(score, SYNC_BURST_SUSPICION_FLOOR)
    elif any(c.author_count >= 3 for c in fuzzy_clusters):
        score = max(score, 0.55)
    elif any(c.author_count >= 2 for c in fuzzy_clusters):
        score = max(score, TWO_AUTHOR_FUZZY_FLOOR)

    if pollination_hit_count >= 3:
        score = max(score, 0.6)
    elif pollination_hit_count >= 1:
        score = max(score, 0.45)

    return round(min(1.0, score), 4)


def merge_coordination_scores(graph_score: float, text_score: float) -> tuple[float, float]:
    combined = round(min(1.0, max(graph_score, text_score)), 4)
    organic = round(1.0 - combined, 4)
    return combined, organic


def collect_text_signals(
    duplicate_clusters: list[DuplicateCluster],
    fuzzy_clusters: list[CrossAuthorFuzzyCluster],
) -> list[str]:
    """Detailed text-coordination signal strings (graph signals kept separate)."""
    _, dup_signals = apply_duplicate_temporal_cib_boost(0.0, [], duplicate_clusters)
    _, fuzzy_signals = apply_cross_author_fuzzy_cib_boost(0.0, [], fuzzy_clusters)
    return dup_signals + fuzzy_signals
