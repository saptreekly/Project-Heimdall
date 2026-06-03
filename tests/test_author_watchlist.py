import pytest

from heimdall.ingestion.author_watchlist import (
    AuthorWatchlistStore,
    NarrativeWatchlist,
    WatchAuthor,
    apply_pipeline_discoveries,
    build_author_poll_plan,
    context_terms_from_keywords,
    pick_author_for_poll,
    register_author_discovery,
    resolve_x_scheduled_mode,
)
from heimdall.ingestion.query_plan import build_author_poll_query


def test_build_author_poll_query_includes_from_since_and_exclude() -> None:
    q = build_author_poll_query(
        "PolReporter",
        context_terms=["2026 midterms", "election fraud"],
        exclude_terms=("$SPX", "btc"),
        since_date="2026-06-01",
    )
    assert q.startswith("from:PolReporter")
    assert "2026 midterms" in q or '"2026 midterms"' in q
    assert "since:2026-06-01" in q
    assert "-(" in q


def test_context_terms_from_keywords_skips_lists() -> None:
    terms = context_terms_from_keywords(
        ["list:123", "2026 midterms", "2026 red wave"],
        max_terms=5,
    )
    assert "list:123" not in terms
    assert "2026 midterms" in terms


def test_register_and_pick_author_for_poll(tmp_path, monkeypatch) -> None:
    path = tmp_path / "watchlist.json"
    monkeypatch.setenv("X_AUTHOR_WATCHLIST_PATH", str(path))

    register_author_discovery(
        "midterms_2026",
        author_id="111",
        handle="alpha",
        discovered_via="keyword",
        depth=0,
        inserted_delta=2,
    )
    register_author_discovery(
        "midterms_2026",
        author_id="222",
        handle="beta",
        discovered_via="keyword",
        depth=0,
        inserted_delta=1,
    )

    picked = pick_author_for_poll("midterms_2026")
    assert picked is not None
    assert picked.author_id == "111"


def test_resolve_x_scheduled_mode_alternates(tmp_path, monkeypatch) -> None:
    path = tmp_path / "watchlist.json"
    monkeypatch.setenv("X_AUTHOR_WATCHLIST_PATH", str(path))
    monkeypatch.setenv("X_AUTHOR_POLL_EVERY_N", "2")

    store = AuthorWatchlistStore.load()
    store.narratives["midterms_2026"] = NarrativeWatchlist(
        authors={
            "111": WatchAuthor(author_id="111", handle="alpha", priority=0.9),
        }
    )
    store.save()

    mode1, _, _ = resolve_x_scheduled_mode("midterms_2026", store=AuthorWatchlistStore.load())
    assert mode1 == "keyword"

    mode2, author, _ = resolve_x_scheduled_mode("midterms_2026", store=AuthorWatchlistStore.load())
    assert mode2 == "author_poll"
    assert author is not None
    assert author.author_id == "111"


def test_build_author_poll_plan_single_query() -> None:
    author = WatchAuthor(author_id="1", handle="reporter", last_polled_at="2026-06-01T00:00:00+00:00")
    plan = build_author_poll_plan(
        author,
        context_terms=["midterms"],
        limit=20,
        exclude_terms=("btc",),
    )
    assert len(plan.queries) == 1
    assert plan.queries[0].query_type == "author_poll"
    assert plan.queries[0].platform_query.startswith("from:reporter")


def test_apply_pipeline_discoveries_skips_bots(tmp_path, monkeypatch) -> None:
    path = tmp_path / "watchlist.json"
    monkeypatch.setenv("X_AUTHOR_WATCHLIST_PATH", str(path))

    apply_pipeline_discoveries(
        "midterms_2026",
        [{"author_id": "bot1", "handle": "bot", "discovered_via": "keyword", "depth": 0, "inserted": 1}],
        bot_author_ids={"bot1"},
    )
    store = AuthorWatchlistStore.load()
    assert "bot1" not in store.narrative("midterms_2026").authors
