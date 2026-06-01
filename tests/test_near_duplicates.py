from heimdall.analysis.near_duplicates import (
    apply_cross_author_fuzzy_cib_boost,
    copypasta_scores,
    find_cross_author_fuzzy_clusters,
    find_near_duplicate_groups,
    jaccard_similarity,
    token_set,
)


def test_jaccard_identical() -> None:
    a = token_set("America loves winners and won't tolerate losers")
    b = token_set("america loves winners and won't tolerate losers")
    assert jaccard_similarity(a, b) == 1.0


def test_jaccard_spacing_variant() -> None:
    long = (
        "america loves winners and won't tolerate these pathetic losers "
        "in the twenty twenty six midterms fight today"
    )
    a = token_set(long)
    b = token_set(long.replace("pathetic", "path etic"))
    assert jaccard_similarity(a, b) >= 0.82


def test_near_duplicate_groups_same_author() -> None:
    author = "user1"
    t1 = (
        "I feel sorry for that senile coward facist nazi pig bonespur draft dodger "
        "america loves winners won't tolerate these pathetic losers"
    )
    t2 = (
        "I feel sorry for that senile cow ard facist nazi pig bonespur draft dodger "
        "america loves winners won't tolerate these pathetic losers"
    )
    rows = [
        (1, author, t1, "2026-06-01T01:14:24"),
        (2, author, t2, "2026-06-01T01:14:48"),
        (3, author, "completely unrelated post about weather and sports today", "2026-06-01T02:00:00"),
    ]
    groups = find_near_duplicate_groups(rows, threshold=0.82, min_posts=2)
    assert len(groups) == 1
    assert set(groups[0].post_ids) == {1, 2}


def test_cross_author_fuzzy_clusters() -> None:
    base = (
        "america loves winners and won't tolerate these pathetic losers "
        "in the twenty twenty six midterms fight today"
    )
    rows = [
        (1, "author_a", base, "2026-06-01T10:00:00"),
        (2, "author_b", base.replace("pathetic", "path etic"), "2026-06-01T10:00:30"),
        (3, "author_c", base.replace("fight", "figh t"), "2026-06-01T10:01:00"),
        (4, "author_d", "unrelated weather forecast for the weekend only here", "2026-06-01T12:00:00"),
    ]
    clusters = find_cross_author_fuzzy_clusters(rows, threshold=0.82, min_authors=2)
    assert len(clusters) >= 1
    top = clusters[0]
    assert top.author_count >= 2
    assert len(set(top.post_ids) & {1, 2, 3}) >= 2


def test_cross_author_skips_single_author_only() -> None:
    author = "solo"
    rows = [
        (1, author, "alpha beta gamma delta epsilon zeta", "2026-06-01T01:00:00"),
        (2, author, "alpha beta gamma delta epsilon zeta eta", "2026-06-01T01:01:00"),
    ]
    assert find_cross_author_fuzzy_clusters(rows) == []


def test_cross_author_fuzzy_cib_boost() -> None:
    from heimdall.analysis.near_duplicates import CrossAuthorFuzzyCluster

    cluster = CrossAuthorFuzzyCluster(
        cluster_id=0,
        post_ids=[1, 2, 3],
        author_ids=["a", "b", "c"],
        author_count=3,
        count=3,
        sample_text="sample",
        max_similarity=0.9,
        burst_synchronized=True,
        burst_author_count=3,
    )
    suspicion, signals = apply_cross_author_fuzzy_cib_boost(0.1, [], [cluster])
    assert suspicion >= 0.72
    assert any("cross_author_fuzzy" in s for s in signals)
    assert any("synchronized_fuzzy_burst" in s for s in signals)


def test_copypasta_scores() -> None:
    rows = [
        (1, "a", "alpha beta gamma delta"),
        (2, "a", "alpha beta gamma epsilon"),
    ]
    scores = copypasta_scores(rows, template_tokens=token_set(rows[0][2]))
    assert scores[1] == 1.0
    assert scores[2] > 0.5
