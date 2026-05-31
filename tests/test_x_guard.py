import pytest

from heimdall.ingestion.x_guard import (
    XDailyBudgetExceeded,
    XIngestDisabled,
    count_graphql_requests,
    plan_x_ingest,
    reserve_daily_requests,
)


def test_plan_trims_keywords_and_limit(monkeypatch) -> None:
    monkeypatch.setenv("X_MAX_KEYWORDS_PER_INGEST", "3")
    monkeypatch.setenv("X_MAX_POSTS_PER_INGEST", "50")
    from heimdall.config import get_settings

    get_settings.cache_clear()

    plan = plan_x_ingest(["a", "b", "c", "d", "e"], limit=100)
    assert len(plan.keywords) == 3
    assert plan.limit == 50
    assert plan.graphql_requests == 3
    assert any("Trimmed" in n for n in plan.notes)
    assert any("Reduced limit" in n for n in plan.notes)


def test_daily_budget_enforced(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "x_rate_state.json"
    monkeypatch.setenv("X_MAX_GRAPHQL_REQUESTS_PER_DAY", "2")
    monkeypatch.setattr("heimdall.ingestion.x_guard._STATE_PATH", state_file)
    from heimdall.config import get_settings

    get_settings.cache_clear()

    import asyncio

    async def run() -> None:
        await reserve_daily_requests(1)
        await reserve_daily_requests(1)
        with pytest.raises(XDailyBudgetExceeded):
            await reserve_daily_requests(1)

    asyncio.run(run())


def test_ingest_disabled(monkeypatch) -> None:
    monkeypatch.setenv("X_INGEST_ENABLED", "false")
    from heimdall.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(XIngestDisabled):
        plan_x_ingest(["test"], limit=10)


def test_count_requests_ignores_blank() -> None:
    assert count_graphql_requests(["a", "  ", "b"]) == 2
