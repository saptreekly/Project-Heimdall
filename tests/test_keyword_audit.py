"""Tests for keyword audit and gap discovery."""

from scripts.keyword_audit import (
    KeywordStats,
    aggregate_keyword_stats,
    discover_gaps,
    is_lifetime_protected,
    keyword_covers,
    keyword_covers_any,
    validate_keyword_query,
)


def test_keyword_covers() -> None:
    assert keyword_covers("2026 midterms", "midterms")
    assert keyword_covers("2026 red wave", "wave")
    assert not keyword_covers("2026 midterms", "deportations")


def test_aggregate_keyword_stats() -> None:
    runs = [
        {"keywords": ["2026 midterms"], "fetched": 10, "inserted": 3},
        {"keywords": ["2026 red wave"], "fetched": 0, "inserted": 0},
        {"keywords": ["2026 midterm fraud"], "fetched": 5, "inserted": 1},
    ]
    stats = aggregate_keyword_stats(runs, ["2026 midterms", "2026 red wave", "2026 midterm fraud"])
    by_kw = {s.keyword: s for s in stats}
    assert by_kw["2026 midterms"].inserted == 3
    assert by_kw["2026 red wave"].inserted == 0


def test_discover_gaps_suggests_uncovered_terms() -> None:
    configured = ["2026 midterms", "2026 red wave"]
    theme_terms = [("deportations", 5.0, "theme cluster (deportations, 8 posts)")]
    suggestions = discover_gaps(
        configured,
        post_texts=["election fraud midterm vote"] * 5,
        theme_terms=theme_terms,
        max_suggestions=5,
    )
    assert suggestions
    assert any("deportations" in s.query for s in suggestions)
    assert not keyword_covers_any(configured, "deportations")


def test_validate_keyword_query_rejects_theme_junk() -> None:
    assert validate_keyword_query("2026 disaster looms") == (False, "blocked token")
    assert validate_keyword_query("2026 hulhumale phase") == (False, "blocked token")
    assert validate_keyword_query("2026 state setting") == (False, "blocked token")
    assert validate_keyword_query("2026 congress post") == (False, "blocked token")
    assert validate_keyword_query("2026 poll spells") == (False, "blocked token")
    assert validate_keyword_query("2026 red wave") == (True, "")
    assert validate_keyword_query("2026 election integrity") == (True, "")
    assert validate_keyword_query("2026 midwest democrat") == (True, "")


def test_is_lifetime_protected() -> None:
    assert is_lifetime_protected(KeywordStats("k", runs=44, inserted=174))
    assert is_lifetime_protected(KeywordStats("k", runs=10, inserted=3))
    assert not is_lifetime_protected(KeywordStats("k", runs=4, inserted=0))
