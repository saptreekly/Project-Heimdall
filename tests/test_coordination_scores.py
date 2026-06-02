"""Tests for split graph vs text coordination scoring."""

from datetime import UTC, datetime

from heimdall.analysis.coordination_scores import (
    compute_text_coordination_score,
    graph_coverage_pct,
    is_graph_sufficient,
    merge_coordination_scores,
)
from heimdall.analysis.duplicates import find_duplicate_clusters_from_rows
from heimdall.analysis.near_duplicates import (
    CrossAuthorFuzzyCluster,
    find_cross_author_fuzzy_clusters,
)


def _fuzzy_cluster(*, author_count: int = 2, burst: bool = False) -> CrossAuthorFuzzyCluster:
    authors = [f"a{i}" for i in range(author_count)]
    return CrossAuthorFuzzyCluster(
        cluster_id=1,
        post_ids=list(range(author_count)),
        author_ids=authors,
        author_count=author_count,
        count=author_count,
        sample_text="fuzzy sample",
        max_similarity=0.95,
        burst_synchronized=burst,
        burst_author_count=author_count if burst else 0,
    )


def test_two_author_fuzzy_raises_text_score() -> None:
    score = compute_text_coordination_score([], [_fuzzy_cluster(author_count=2)])
    assert score >= 0.38


def test_graph_zero_text_fuzzy_combined() -> None:
    text = compute_text_coordination_score([], [_fuzzy_cluster(author_count=2)])
    combined, organic = merge_coordination_scores(0.0, text)
    assert combined == text
    assert organic == round(1.0 - text, 4)


def test_graph_insufficient_with_sparse_edges() -> None:
    assert is_graph_sufficient(6, 6, 165) is False
    assert graph_coverage_pct(6, 165) == round(100 * 6 / 165, 1)


def test_duplicate_rows_two_author_integration() -> None:
    now = datetime.now(tz=UTC)
    rows = [
        (1, "a1", "identical tweet text", now),
        (2, "a2", "identical tweet text", now),
    ]
    dupes = find_duplicate_clusters_from_rows(rows)
    near = [(r[0], r[1], r[2], r[3].isoformat()) for r in rows]
    fuzzy = find_cross_author_fuzzy_clusters(near)
    score = compute_text_coordination_score(dupes, fuzzy)
    assert score >= 0.32
