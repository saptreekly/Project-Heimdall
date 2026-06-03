from heimdall.db.models import Platform
from heimdall.ingestion.query_plan import QueryPlanOptions, build_query_plan


def test_x_query_quotes_phrases() -> None:
    plan = build_query_plan(
        Platform.X,
        ["2026 red wave", "election fraud"],
        40,
        options=QueryPlanOptions(x_exclude_terms=("$SPX", "btc")),
    )
    assert len(plan.queries) == 2
    assert '"2026 red wave"' in plan.queries[0].platform_query
    assert "-(" in plan.queries[0].platform_query
    assert plan.queries[0].query_type == "search"


def test_mastodon_multi_hashtag_variants() -> None:
    plan = build_query_plan(Platform.MASTODON, ["red wave"], 30)
    tags = {q.platform_query for q in plan.queries}
    assert "red" in tags
    assert "redwave" in tags


def test_hn_per_keyword_queries() -> None:
    plan = build_query_plan(Platform.HACKERNEWS, ["alpha", "beta"], 20)
    assert len(plan.queries) == 2
    assert plan.queries[0].platform_query == "alpha"
    assert plan.queries[1].platform_query == "beta"


def test_reddit_subreddit_prefix() -> None:
    plan = build_query_plan(
        Platform.REDDIT,
        ["election fraud"],
        30,
        options=QueryPlanOptions(reddit_subreddits=("politics",)),
    )
    assert plan.queries[0].platform_query.startswith("r/politics:")
    assert "election fraud" in plan.queries[0].platform_query
