import numpy as np
import pytest

from heimdall.nlp.theme_clusters import (
    EMERGING_LEXICON_MAX,
    cluster_posts,
    report_to_dict,
)


def _synthetic_embeddings(n: int, *, groups: list[tuple[int, int]]) -> np.ndarray:
    """Build unit vectors with tight groups for clustering tests."""
    dim = 16
    vectors = np.random.default_rng(42).standard_normal((n, dim)).astype(np.float32)
    for start, count in groups:
        center = np.random.default_rng(start).standard_normal(dim).astype(np.float32)
        center /= np.linalg.norm(center) + 1e-9
        for i in range(count):
            idx = start + i
            if idx < n:
                noise = np.random.default_rng(idx).standard_normal(dim).astype(np.float32) * 0.02
                vec = center + noise
                vectors[idx] = vec / (np.linalg.norm(vec) + 1e-9)
    return vectors


def _mock_two_group_labels(embeddings: np.ndarray) -> tuple[np.ndarray, str]:
    labels = np.zeros(len(embeddings), dtype=int)
    if len(labels) >= 4:
        labels[3:] = 1
    return labels, "test"


def test_cluster_posts_detects_emerging_low_lexicon_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = [
        (1, "zorbax flim flam cascade protocol"),
        (2, "zorbax flim cascade variant"),
        (3, "zorbax protocol flim cascade"),
        (4, "unrelated neutral weather forecast today"),
        (5, "another neutral weather update"),
    ]
    embeddings = _synthetic_embeddings(5, groups=[(0, 3), (3, 2)])

    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters.encode_texts",
        lambda texts, **kwargs: (embeddings[: len(texts)], "test-model"),
    )
    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters._cluster_labels",
        _mock_two_group_labels,
    )

    report = cluster_posts(posts, narrative_id=9)
    assert report.post_count == 5
    assert report.cluster_count >= 2
    emerging = [c for c in report.clusters if c.emerging_theme]
    assert emerging, "expected a lexicon-light cohesive cluster"
    assert emerging[0].lexicon_hit_rate <= EMERGING_LEXICON_MAX
    assert report.post_theme_boost, "emerging cluster should assign outrage boosts"
    assert 1 in report.post_theme_boost


def test_cluster_posts_lexicon_heavy_not_emerging(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = [
        (1, "deep state vermin wake up!!! destroying our country"),
        (2, "deep state vermin wake up share before they delete"),
        (3, "deep state vermin destroying our country wake up"),
    ]
    embeddings = _synthetic_embeddings(3, groups=[(0, 3)])
    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters.encode_texts",
        lambda texts, **kwargs: (embeddings[: len(texts)], "test-model"),
    )
    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters._cluster_labels",
        lambda emb: (np.zeros(len(emb), dtype=int), "test"),
    )
    report = cluster_posts(posts, narrative_id=1)
    assert all(not c.emerging_theme for c in report.clusters)


def test_report_to_dict_shape() -> None:
    report = cluster_posts([], narrative_id=0)
    data = report_to_dict(report)
    assert data["cluster_count"] == 0
    assert data["emerging_theme_count"] == 0


def test_outrage_analyzer_applies_theme_boost(monkeypatch: pytest.MonkeyPatch) -> None:
    from heimdall.nlp.outrage import OutrageAnalyzer

    posts = [(i, f"zorbax theme phrase number {i}") for i in range(1, 5)]
    embeddings = _synthetic_embeddings(4, groups=[(0, 4)])
    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters.encode_texts",
        lambda texts, **kwargs: (embeddings[: len(texts)], "test-model"),
    )
    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters._cluster_labels",
        lambda emb: (np.zeros(len(emb), dtype=int), "test"),
    )

    analyzer = OutrageAnalyzer(use_embeddings=True)
    boosts, emerging = analyzer._theme_context(
        [
            type("P", (), {"id": pid, "text": text, "narrative_id": 1})()
            for pid, text in posts
        ]
    )
    base = analyzer.analyze(posts[0][1]).outrage_index
    boosted = analyzer.analyze(
        posts[0][1],
        theme_boost=boosts.get(1, 0.0),
        emerging_theme=emerging.get(1, False),
    ).outrage_index
    if boosts:
        assert boosted >= base
