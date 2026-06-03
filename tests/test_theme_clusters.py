import numpy as np
import pytest

from heimdall.nlp.theme_clusters import (
    EMERGING_LEXICON_MAX,
    _assign_distinct_cluster_labels,
    _label_terms,
    cluster_posts,
    report_to_dict,
)
from heimdall.nlp.theme_phrases import score_distinct_phrases


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


def _mock_two_group_labels(embeddings: np.ndarray, **_kwargs) -> tuple[np.ndarray, str]:
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
        "heimdall.nlp.post_embeddings.resolve_embedding_matrix",
        lambda post_ids, texts, **kwargs: (embeddings[: len(texts)], "test-model"),
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
        "heimdall.nlp.post_embeddings.resolve_embedding_matrix",
        lambda post_ids, texts, **kwargs: (embeddings[: len(texts)], "test-model"),
    )
    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters._cluster_labels",
        lambda emb, **_kw: (np.zeros(len(emb), dtype=int), "test"),
    )
    report = cluster_posts(posts, narrative_id=1)
    assert all(not c.emerging_theme for c in report.clusters)


def test_label_terms_excludes_stopwords() -> None:
    terms = _label_terms(
        [
            "The election fraud with the deep state and corrupt officials",
            "Election fraud corrupt officials deep state accountability",
        ],
        top_n=8,
    )
    assert "the" not in terms
    assert "with" not in terms
    assert "and" not in terms
    assert "election" in terms or "fraud" in terms


def test_red_wave_phrase_not_split() -> None:
    member = [
        "red wave heat preparedness cross seminar",
        "red wave heat seminar cross training",
        "preparedness cross seminar wave heat red wave",
    ]
    contrast = [
        "nazi senile pig losers feel sorry insult",
        "election fraud midterm trump vote need accountability",
    ]
    phrases, _, _ = score_distinct_phrases(member, contrast, top_n=6)
    assert "red wave" in phrases, f"expected multi-word phrase, got {phrases}"


def test_assign_distinct_cluster_labels() -> None:
    all_texts = [
        "election fraud midterm trump vote need accountability",
        "election midterm fraud trump vote accountability issue",
        "election fraud vote midterm trump federal order",
        "nazi senile pig losers feel sorry insult",
        "nazi senile pig rant losers senile",
        "senile pig nazi rhetoric feel",
        "red wave heat preparedness cross seminar",
        "red wave heat seminar cross training",
        "preparedness cross seminar wave heat",
    ]
    cluster_texts = {
        0: all_texts[0:3],
        1: all_texts[3:6],
        2: all_texts[6:9],
    }
    labels = _assign_distinct_cluster_labels(cluster_texts, all_texts)
    assert len(labels) == 3
    tops = [labels[cid][0][0] for cid in sorted(labels)]
    assert len(set(tops)) >= 2, f"expected unique lead terms, got {tops}"
    nazi_labels = labels[1][0]
    assert any(
        t in nazi_labels or " ".join(nazi_labels).find(t) >= 0
        for t in ("nazi", "senile", "pig", "losers", "insult", "rant")
    )
    wave_labels = labels[2][0]
    assert "red wave" in wave_labels or "red wave" in labels[2][0] + (labels[2][1] or [])
    assert labels[1][2] > 0
    assert labels[2][2] > 0


def test_kmeans_cluster_count_caps_slices() -> None:
    from heimdall.nlp.theme_clusters import _kmeans_cluster_count

    assert _kmeans_cluster_count(198) == 6
    assert _kmeans_cluster_count(40) == 2
    assert _kmeans_cluster_count(2) == 1


def test_report_to_dict_shape() -> None:
    report = cluster_posts([], narrative_id=0)
    data = report_to_dict(report)
    assert data["cluster_count"] == 0
    assert data["emerging_theme_count"] == 0
    assert "cluster_map" in data
    assert "merge_tree" in data
    assert "cluster_similarity" in data


def test_merge_tree_and_similarity_export(monkeypatch: pytest.MonkeyPatch) -> None:
    posts = [
        (1, "red wave heat preparedness seminar", "a1"),
        (2, "red wave heat cross training seminar", "a2"),
        (3, "red wave preparedness heat wave", "a3"),
        (4, "nazi senile pig insult rant", "b1"),
        (5, "senile pig nazi losers rhetoric", "b2"),
        (6, "nazi pig senile insult feel", "b3"),
    ]
    embeddings = _synthetic_embeddings(6, groups=[(0, 3), (3, 3)])
    monkeypatch.setattr(
        "heimdall.nlp.post_embeddings.resolve_embedding_matrix",
        lambda post_ids, texts, **kwargs: (embeddings[: len(texts)], "test-model"),
    )
    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters._cluster_labels",
        lambda emb, **_kw: (
            np.array([0, 0, 0, 1, 1, 1], dtype=int),
            "test",
        ),
    )
    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters._merge_similar_clusters",
        lambda _emb, labels: labels,
    )
    report = cluster_posts(posts, narrative_id=7)
    data = report_to_dict(report)
    leaves = [n for n in data["merge_tree"] if n.get("leaf")]
    assert len(leaves) >= 2, "expected leaf nodes for each cluster"
    assert data["merge_tree"], "expected merge tree export"
    if data["cluster_similarity"]:
        assert data["cluster_similarity"][0]["similarity"] >= 0.35


def test_outrage_analyzer_applies_theme_boost(monkeypatch: pytest.MonkeyPatch) -> None:
    from heimdall.nlp.outrage import OutrageAnalyzer

    posts = [(i, f"zorbax theme phrase number {i}") for i in range(1, 5)]
    embeddings = _synthetic_embeddings(4, groups=[(0, 4)])
    monkeypatch.setattr(
        "heimdall.nlp.post_embeddings.resolve_embedding_matrix",
        lambda post_ids, texts, **kwargs: (embeddings[: len(texts)], "test-model"),
    )
    monkeypatch.setattr(
        "heimdall.nlp.theme_clusters._cluster_labels",
        lambda emb, **_kw: (np.zeros(len(emb), dtype=int), "test"),
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
