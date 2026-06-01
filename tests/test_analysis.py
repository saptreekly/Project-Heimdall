from datetime import UTC, datetime

import pandas as pd

from heimdall.analysis.duplicates import (
    find_duplicate_clusters_from_rows,
    find_duplicate_text_clusters,
    normalize_text,
)


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("  Hello   WORLD ") == "hello world"


def test_duplicate_clusters_cross_author() -> None:
    posts = pd.DataFrame(
        {
            "post_id": [1, 2, 3],
            "author_id": ["a", "b", "c"],
            "text": [
                "Sidney Powell RELEASE THE KRAKEN",
                "Sidney Powell RELEASE THE KRAKEN",
                "unique post",
            ],
        }
    )
    clusters = find_duplicate_text_clusters(posts, min_posts=2)
    assert len(clusters) == 1
    assert clusters[0].count == 2
    assert set(clusters[0].author_ids) == {"a", "b"}


def test_duplicate_clusters_from_rows() -> None:
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    rows = [
        (10, "u1", "Same message", base),
        (11, "u2", "Same message", base),
        (12, "u3", "other", base),
    ]
    clusters = find_duplicate_clusters_from_rows(rows, min_posts=2)
    assert len(clusters) == 1
    assert clusters[0].count == 2
    assert clusters[0].post_ids == [10, 11]
