"""Conservative rate limits for unofficial X GraphQL ingest (session cookies)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from heimdall.config import get_settings

_LIST_PREFIX = "list:"
_file_lock = asyncio.Lock()


def _state_path() -> Path:
    return Path(get_settings().x_rate_state_path)


class XIngestDisabled(Exception):
    """X ingest turned off via X_INGEST_ENABLED=false."""


class XDailyBudgetExceeded(Exception):
    """Daily GraphQL request budget exhausted."""


@dataclass(frozen=True)
class XIngestPlan:
    keywords: list[str]
    limit: int
    graphql_requests: int
    notes: list[str]
    search_product: str = "Latest"


def count_graphql_requests(keywords: list[str]) -> int:
    return sum(1 for k in keywords if k.strip())


def plan_x_ingest(
    keywords: list[str],
    limit: int,
    *,
    graphql_requests: int | None = None,
    search_product: str = "Latest",
) -> XIngestPlan:
    settings = get_settings()
    notes: list[str] = []

    if not settings.x_ingest_enabled:
        raise XIngestDisabled(
            "X ingest is disabled (X_INGEST_ENABLED=false). "
            "Set true in .env to re-enable."
        )

    cleaned = [k.strip() for k in keywords if k.strip()]
    if not cleaned:
        raise ValueError("At least one non-empty keyword is required for X ingest.")

    if len(cleaned) > settings.x_max_keywords_per_ingest:
        dropped = len(cleaned) - settings.x_max_keywords_per_ingest
        notes.append(
            f"Trimmed {dropped} keyword(s) to X_MAX_KEYWORDS_PER_INGEST="
            f"{settings.x_max_keywords_per_ingest}."
        )
        cleaned = cleaned[: settings.x_max_keywords_per_ingest]

    capped_limit = min(limit, settings.x_max_posts_per_ingest)
    if capped_limit < limit:
        notes.append(
            f"Reduced limit from {limit} to X_MAX_POSTS_PER_INGEST={capped_limit}."
        )

    requests = graphql_requests if graphql_requests is not None else count_graphql_requests(cleaned)
    return XIngestPlan(
        keywords=cleaned,
        limit=capped_limit,
        graphql_requests=requests,
        notes=notes,
        search_product=search_product,
    )


def max_tweets_per_search(plan: XIngestPlan) -> int:
    settings = get_settings()
    per_query = max(plan.limit // max(len(plan.keywords), 1), 1)
    return min(per_query, settings.x_max_tweets_per_search)


async def wait_between_searches() -> None:
    await asyncio.sleep(get_settings().x_min_seconds_between_searches)


async def reserve_daily_requests(count: int) -> dict:
    settings = get_settings()
    cap = settings.x_max_graphql_requests_per_day
    path = _state_path()
    today = date.today().isoformat()

    async with _file_lock:
        state: dict = {"date": today, "requests_used": 0}
        if path.is_file():
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {"date": today, "requests_used": 0}
        if state.get("date") != today:
            state = {"date": today, "requests_used": 0}

        used = int(state.get("requests_used", 0))
        if used + count > cap:
            raise XDailyBudgetExceeded(
                f"Daily GraphQL budget exceeded ({used}/{cap} used, need {count})."
            )
        state["requests_used"] = used + count
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    return {
        "requests_used_today": state["requests_used"],
        "requests_daily_cap": cap,
        "requests_remaining": cap - state["requests_used"],
    }


async def daily_usage_snapshot() -> dict:
    settings = get_settings()
    cap = settings.x_max_graphql_requests_per_day
    path = _state_path()
    today = date.today().isoformat()
    used = 0
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state.get("date") == today:
                used = int(state.get("requests_used", 0))
        except json.JSONDecodeError:
            used = 0
    return {
        "requests_used_today": used,
        "requests_daily_cap": cap,
        "requests_remaining": max(cap - used, 0),
    }
