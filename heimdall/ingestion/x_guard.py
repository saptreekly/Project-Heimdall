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


def count_graphql_requests(keywords: list[str]) -> int:
    return sum(1 for k in keywords if k.strip())


def plan_x_ingest(keywords: list[str], limit: int) -> XIngestPlan:
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

    requests = count_graphql_requests(cleaned)
    return XIngestPlan(
        keywords=cleaned,
        limit=capped_limit,
        graphql_requests=requests,
        notes=notes,
    )


def max_tweets_per_search(plan: XIngestPlan) -> int:
    settings = get_settings()
    per_query = max(plan.limit // max(len(plan.keywords), 1), 1)
    return min(per_query, settings.x_max_tweets_per_search)


async def reserve_daily_requests(count: int) -> dict:
    """Reserve GraphQL calls for today; raises if over X_MAX_GRAPHQL_REQUESTS_PER_DAY."""
    settings = get_settings()
    async with _file_lock:
        state = _load_state()
        today = date.today().isoformat()
        if state.get("date") != today:
            state = {"date": today, "count": 0}

        used = int(state.get("count", 0))
        cap = settings.x_max_graphql_requests_per_day
        if used + count > cap:
            raise XDailyBudgetExceeded(
                f"X daily GraphQL budget exceeded ({used}/{cap} used today). "
                f"This ingest needs {count} request(s). "
                "Try again tomorrow, lower keywords/limit, or raise "
                "X_MAX_GRAPHQL_REQUESTS_PER_DAY in .env (higher ban risk)."
            )

        state["count"] = used + count
        _save_state(state)
        return {
            "date": today,
            "requests_reserved": count,
            "requests_used_today": state["count"],
            "requests_daily_cap": cap,
        }


async def wait_between_searches() -> None:
    settings = get_settings()
    delay = settings.x_min_seconds_between_searches
    if delay > 0:
        await asyncio.sleep(delay)


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {"date": date.today().isoformat(), "count": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"date": date.today().isoformat(), "count": 0}


def _save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


async def daily_usage_snapshot() -> dict:
    async with _file_lock:
        state = _load_state()
        today = date.today().isoformat()
        if state.get("date") != today:
            used = 0
        else:
            used = int(state.get("count", 0))
        cap = get_settings().x_max_graphql_requests_per_day
        return {
            "date": today,
            "requests_used_today": used,
            "requests_daily_cap": cap,
            "requests_remaining": max(cap - used, 0),
        }
