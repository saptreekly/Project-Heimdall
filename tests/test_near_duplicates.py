from heimdall.analysis.near_duplicates import (
    copypasta_scores,
    find_near_duplicate_groups,
    jaccard_similarity,
    token_set,
)


def test_jaccard_identical() -> None:
    a = token_set("America loves winners and won't tolerate losers")
    b = token_set("america loves winners and won't tolerate losers")
    assert jaccard_similarity(a, b) == 1.0


def test_jaccard_spacing_variant() -> None:
    a = token_set("senile coward facist nazi pig")
    b = token_set("senile cow ard facist nazi pig")
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


def test_copypasta_scores() -> None:
    rows = [
        (1, "a", "alpha beta gamma delta"),
        (2, "a", "alpha beta gamma epsilon"),
    ]
    scores = copypasta_scores(rows, template_tokens=token_set(rows[0][2]))
    assert scores[1] == 1.0
    assert scores[2] > 0.5
