#!/usr/bin/env python3
"""
Run configured ingest jobs for CI / cron.

Respects X guardrails (plan_x_ingest, daily GraphQL budget, keyword/limit caps).
Writes to DATABASE_URL (default data/dashboard/heimdall.db).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "scheduled_ingest.json"
DEFAULT_DB = ROOT / "data" / "dashboard" / "heimdall.db"
DEFAULT_ROTATION = ROOT / "data" / "dashboard" / "x_keyword_rotation.json"
DEFAULT_INGEST_LOG = ROOT / "data" / "dashboard" / "ingest_runs.jsonl"

EXPLORE_MIN_RUNS = 2
YIELD_CANDIDATE_POOL = 3
X_SEARCH_PRODUCTS = ("Latest", "Top")


@dataclass(frozen=True)
class IngestJob:
    narrative_name: str
    platform: str
    keywords: list[str]
    limit: int
    fallback_platforms: tuple[str, ...] = ()
    x_exclude_terms: tuple[str, ...] = ()
    x_list_sources: tuple[str, ...] = ()
    reddit_subreddits: tuple[str, ...] = ("politics", "news", "Conservative")
    rotation_strategy: str = "round_robin"
    author_watch_enabled: bool = True


def load_jobs(path: Path) -> list[IngestJob]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    jobs: list[IngestJob] = []
    for item in raw.get("jobs", []):
        jobs.append(
            IngestJob(
                narrative_name=item["narrative_name"],
                platform=item["platform"].lower(),
                keywords=list(item["keywords"]),
                limit=int(item["limit"]),
                fallback_platforms=tuple(item.get("fallback_platforms") or ()),
                x_exclude_terms=tuple(item.get("x_exclude_terms") or ()),
                x_list_sources=tuple(item.get("x_list_sources") or ()),
                reddit_subreddits=tuple(
                    item.get("reddit_subreddits") or ("politics", "news", "Conservative")
                ),
                rotation_strategy=str(item.get("rotation_strategy") or "round_robin"),
                author_watch_enabled=bool(item.get("author_watch_enabled", True)),
            )
        )
    return jobs


def _x_credentials_present() -> bool:
    from heimdall.config import get_settings

    s = get_settings()
    return bool(s.x_auth_token and s.x_ct0)


def _scheduled_keywords_per_run() -> int | None:
    raw = os.environ.get("X_SCHEDULED_KEYWORDS_PER_RUN", "").strip()
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


def _rotation_state_path() -> Path:
    raw = os.environ.get("X_ROTATION_STATE_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_ROTATION


def _ingest_log_path() -> Path:
    raw = os.environ.get("INGEST_RUNS_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_INGEST_LOG


def _load_keyword_run_counts(keywords: list[str], *, days: int = 14) -> dict[str, int]:
    path = _ingest_log_path()
    if not path.is_file():
        return {kw: 0 for kw in keywords}
    cutoff = datetime.now(UTC) - timedelta(days=days)
    counts: dict[str, int] = defaultdict(int)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        at = row.get("at")
        if at:
            try:
                if datetime.fromisoformat(at.replace("Z", "+00:00")) < cutoff:
                    continue
            except ValueError:
                pass
        for kw in row.get("keywords") or []:
            if kw in keywords:
                counts[kw] += 1
    return {kw: counts.get(kw, 0) for kw in keywords}


def _load_rotation_state() -> dict:
    path = _rotation_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"keyword_index": 0}


def _save_rotation_state(state: dict) -> None:
    path = _rotation_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _load_keyword_yield_stats(keywords: list[str], *, days: int = 14) -> dict[str, float]:
    path = _ingest_log_path()
    if not path.is_file():
        return {kw: 0.0 for kw in keywords}
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"runs": 0, "inserted": 0})
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        at = row.get("at")
        if at:
            try:
                if datetime.fromisoformat(at.replace("Z", "+00:00")) < cutoff:
                    continue
            except ValueError:
                pass
        for kw in row.get("keywords") or []:
            if kw not in keywords:
                continue
            stats[kw]["runs"] += 1
            stats[kw]["inserted"] += int(row.get("inserted") or 0)
    yields: dict[str, float] = {}
    for kw in keywords:
        runs = stats[kw]["runs"]
        yields[kw] = (stats[kw]["inserted"] / runs) if runs else 0.0
    return yields


def rotate_x_keywords(keywords: list[str], count: int) -> tuple[list[str], int]:
    cleaned = [k.strip() for k in keywords if k.strip()]
    if not cleaned or count <= 0:
        return [], 0

    state = _load_rotation_state()
    idx = int(state.get("keyword_index", 0)) % len(cleaned)
    selected = [cleaned[(idx + i) % len(cleaned)] for i in range(min(count, len(cleaned)))]
    state["keyword_index"] = idx + len(selected)
    _save_rotation_state(state)
    return selected, state["keyword_index"]


def select_keywords_explore_yield(keywords: list[str], per_run: int) -> tuple[list[str], str]:
    run_counts = _load_keyword_run_counts(keywords)
    under_sampled = sorted(
        [kw for kw in keywords if run_counts.get(kw, 0) < EXPLORE_MIN_RUNS],
        key=lambda kw: (run_counts.get(kw, 0), kw),
    )
    if under_sampled:
        return under_sampled[:per_run], "explore_under_sampled"

    yields = _load_keyword_yield_stats(keywords)
    ranked = sorted(keywords, key=lambda kw: (-yields.get(kw, 0.0), kw))
    pool_size = max(YIELD_CANDIDATE_POOL, per_run)
    pool = ranked[: min(pool_size, len(ranked))]
    state = _load_rotation_state()
    idx = int(state.get("yield_pick_index", 0)) % len(pool)
    selected = [pool[(idx + i) % len(pool)] for i in range(min(per_run, len(pool)))]
    state["yield_pick_index"] = idx + len(selected)
    _save_rotation_state(state)
    return selected, "yield_pool_rotate"


def rotate_x_search_product() -> str:
    state = _load_rotation_state()
    idx = int(state.get("search_product_index", 0)) % len(X_SEARCH_PRODUCTS)
    product = X_SEARCH_PRODUCTS[idx]
    state["search_product_index"] = idx + 1
    _save_rotation_state(state)
    return product


def select_keywords_for_run(job: IngestJob) -> tuple[list[str], str | None]:
    per_run = _scheduled_keywords_per_run()
    if per_run is None or job.platform != "x":
        return job.keywords, None
    if job.rotation_strategy == "yield":
        yields = _load_keyword_yield_stats(job.keywords)
        ranked = sorted(job.keywords, key=lambda kw: (-yields.get(kw, 0.0), kw))
        return ranked[:per_run], "yield"
    if job.rotation_strategy == "explore_yield":
        return select_keywords_explore_yield(job.keywords, per_run)
    rotated, _ = rotate_x_keywords(job.keywords, per_run)
    return rotated or job.keywords, "round_robin"


def keywords_for_scheduled_job(job: IngestJob) -> list[str]:
    keywords, _ = select_keywords_for_run(job)
    return keywords


def append_ingest_run(row: dict) -> None:
    path = _ingest_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at": datetime.now(UTC).isoformat(), **row}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _ingest_options_from_job(job: IngestJob, **overrides):
    from heimdall.ingestion.ingest_options import IngestOptions

    base = dict(
        x_exclude_terms=job.x_exclude_terms,
        x_list_sources=job.x_list_sources,
        reddit_subreddits=job.reddit_subreddits,
        fallback_platforms=job.fallback_platforms,
    )
    base.update(overrides)
    return IngestOptions(**base)


async def _known_bot_author_ids(author_ids: list[str]) -> set[str]:
    if not author_ids:
        return set()
    from heimdall.datasets.astroturf import lookup_labels
    from heimdall.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        labels = await lookup_labels(db, author_ids)
    return set(labels.keys())


async def _apply_author_watchlist_updates(
    job: IngestJob,
    result: dict,
    *,
    polled_author_id: str | None = None,
) -> None:
    from heimdall.ingestion.author_watchlist import (
        apply_pipeline_discoveries,
        record_author_poll_result,
    )

    discoveries = list(result.get("author_discoveries") or [])
    author_ids = [str(d.get("author_id") or "") for d in discoveries]
    if polled_author_id:
        author_ids.append(polled_author_id)
    bots = await _known_bot_author_ids([a for a in author_ids if a])
    apply_pipeline_discoveries(job.narrative_name, discoveries, bot_author_ids=bots)
    if polled_author_id:
        poll_inserts = int(result.get("inserted") or 0)
        record_author_poll_result(
            job.narrative_name,
            polled_author_id,
            inserts=poll_inserts,
            latest_post_at=result.get("latest_post_at"),
        )


async def run_job_on_platform(
    job: IngestJob,
    platform_name: str,
    keywords: list[str],
    *,
    keyword_selection: str | None = None,
    search_product: str | None = None,
) -> dict:
    from heimdall.config import get_settings
    from heimdall.db.models import Platform
    from heimdall.ingestion.pipeline import IngestionPipeline
    from heimdall.ingestion.query_plan import build_query_plan
    from heimdall.ingestion.x_guard import (
        XDailyBudgetExceeded,
        XIngestDisabled,
        daily_usage_snapshot,
        plan_x_ingest,
    )

    settings = get_settings()
    try:
        platform = Platform(platform_name)
    except ValueError as exc:
        raise ValueError(f"Unknown platform '{platform_name}' in job {job.narrative_name}") from exc

    options = _ingest_options_from_job(job)
    x_plan = None
    polled_author_id: str | None = None
    ingest_mode = "keyword"
    if platform == Platform.X:
        if not _x_credentials_present():
            return {
                "narrative_name": job.narrative_name,
                "platform": platform_name,
                "skipped": True,
                "reason": "AUTH_TOKEN / CT0 not set",
            }
        if not settings.x_ingest_enabled:
            return {
                "narrative_name": job.narrative_name,
                "platform": platform_name,
                "skipped": True,
                "reason": "X_INGEST_ENABLED=false",
            }

        from heimdall.ingestion.author_watchlist import (
            AuthorWatchlistStore,
            build_author_poll_plan,
            context_terms_from_keywords,
            record_author_poll_start,
            resolve_x_scheduled_mode,
        )
        from heimdall.ingestion.query_plan import QueryPlanOptions

        plan_opts = QueryPlanOptions(
            x_exclude_terms=options.x_exclude_terms or QueryPlanOptions().x_exclude_terms,
            x_list_sources=options.x_list_sources,
            reddit_subreddits=options.reddit_subreddits,
        )
        watch_store = AuthorWatchlistStore.load()
        poll_author = None
        poll_options = options
        run_keywords = keywords
        if job.author_watch_enabled:
            ingest_mode, poll_author, watch_store = resolve_x_scheduled_mode(
                job.narrative_name,
                store=watch_store,
            )

        if ingest_mode == "author_poll" and poll_author:
            polled_author_id = poll_author.author_id
            context = context_terms_from_keywords(job.keywords)
            query_plan_override = build_author_poll_plan(
                poll_author,
                context_terms=context,
                limit=job.limit,
                exclude_terms=plan_opts.x_exclude_terms,
            )
            handle = poll_author.handle or poll_author.author_id
            run_keywords = [f"author:{handle.lstrip('@')}"]
            x_plan = plan_x_ingest(
                run_keywords,
                job.limit,
                graphql_requests=1,
                search_product=search_product or "Latest",
            )
            poll_options = _ingest_options_from_job(
                job,
                require_keyword_hit=False,
                query_plan_override=query_plan_override,
            )
            record_author_poll_start(job.narrative_name, poll_author, store=watch_store)
        else:
            ingest_mode = "keyword"
            query_plan = build_query_plan(
                platform,
                keywords,
                job.limit,
                options=plan_opts,
            )
            x_plan = plan_x_ingest(
                keywords,
                job.limit,
                graphql_requests=len(query_plan.queries),
                search_product=search_product or rotate_x_search_product(),
            )

        usage_before = await daily_usage_snapshot()
        if usage_before["requests_remaining"] < x_plan.graphql_requests:
            return {
                "narrative_name": job.narrative_name,
                "platform": platform_name,
                "skipped": True,
                "reason": (
                    f"daily GraphQL budget insufficient "
                    f"({usage_before['requests_used_today']}/{usage_before['requests_daily_cap']} used, "
                    f"need {x_plan.graphql_requests})"
                ),
            }
    else:
        poll_options = options
        run_keywords = keywords

    from heimdall.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        pipeline = IngestionPipeline(db, platform=platform, x_plan=x_plan)
        limit = x_plan.limit if x_plan else job.limit
        try:
            result = await pipeline.ingest_narrative(
                job.narrative_name,
                run_keywords if platform == Platform.X else keywords,
                limit=limit,
                options=poll_options if platform == Platform.X else options,
            )
        except (XDailyBudgetExceeded, XIngestDisabled) as exc:
            return {
                "narrative_name": job.narrative_name,
                "platform": platform_name,
                "skipped": True,
                "reason": str(exc),
            }

    if platform == Platform.X and job.author_watch_enabled and not result.get("skipped"):
        await _apply_author_watchlist_updates(
            job,
            result,
            polled_author_id=polled_author_id,
        )

    out = {"narrative_name": job.narrative_name, "platform": platform_name, **result}
    if platform == Platform.X:
        out["ingest_mode"] = ingest_mode
        if polled_author_id:
            out["polled_author_id"] = polled_author_id
    if x_plan:
        out["planned_keywords"] = x_plan.keywords
        out["planned_limit"] = x_plan.limit
        out["planned_graphql_requests"] = x_plan.graphql_requests
        out["search_product"] = x_plan.search_product
        out["plan_notes"] = x_plan.notes
        if ingest_mode == "keyword" and _scheduled_keywords_per_run() is not None:
            out["scheduled_keyword_rotation"] = True
            out["rotation_strategy"] = job.rotation_strategy
            if keyword_selection:
                out["keyword_selection"] = keyword_selection
    return out


async def run_job(job: IngestJob) -> dict:
    keywords, keyword_selection = select_keywords_for_run(job)
    search_product = rotate_x_search_product() if job.platform == "x" else None
    primary = await run_job_on_platform(
        job,
        job.platform,
        keywords,
        keyword_selection=keyword_selection,
        search_product=search_product,
    )
    if job.platform == "x" and "planned_keywords" not in primary:
        primary["planned_keywords"] = keywords
        if keyword_selection:
            primary.setdefault("keyword_selection", keyword_selection)
        if search_product:
            primary.setdefault("search_product", search_product)
    if not primary.get("skipped"):
        return primary

    attempts = [primary]
    for fallback in job.fallback_platforms:
        if fallback.lower() == job.platform:
            continue
        attempt = await run_job_on_platform(
            job,
            fallback.lower(),
            job.keywords,
            search_product=rotate_x_search_product() if fallback.lower() == "x" else None,
        )
        attempts.append(attempt)
        if not attempt.get("skipped"):
            attempt["fallback_from"] = job.platform
            attempt["primary_skip_reason"] = primary.get("reason")
            return attempt

    primary["fallback_attempts"] = attempts[1:]
    return primary


async def run(config: Path, export: bool) -> int:
    from heimdall.db.session import init_db

    if not config.is_file():
        print(f"Missing config: {config}", file=sys.stderr)
        return 1

    jobs = load_jobs(config)
    if not jobs:
        print("No jobs in config", file=sys.stderr)
        return 1

    DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)
    await init_db()

    results: list[dict] = []
    any_ran = False
    for job in jobs:
        print(f"\n=== {job.narrative_name} ({job.platform}) ===")
        row = await run_job(job)
        results.append(row)
        print(json.dumps(row, indent=2))
        log_row = {
            "narrative_name": job.narrative_name,
            "platform": row.get("platform", job.platform),
            "keywords": row.get("planned_keywords") or job.keywords,
            "skipped": bool(row.get("skipped")),
            "reason": row.get("reason"),
            "fetched": row.get("fetched"),
            "inserted": row.get("inserted"),
            "updated": row.get("updated"),
            "filtered": row.get("filtered"),
            "duplicates": row.get("duplicates"),
            "net_new": row.get("net_new", row.get("inserted")),
            "duplicate_rate": row.get("duplicate_rate"),
            "processed": row.get("processed"),
            "pages_fetched": row.get("pages_fetched"),
            "second_page_triggered": row.get("second_page_triggered"),
            "scored": row.get("scored"),
            "rescored_total": row.get("rescored_total", row.get("scored")),
            "edges": row.get("edges"),
            "keyword_stats": row.get("keyword_stats"),
            "fallback_from": row.get("fallback_from"),
            "ingest_mode": row.get("ingest_mode"),
            "polled_author_id": row.get("polled_author_id"),
            "search_product": row.get("search_product"),
            "keyword_selection": row.get("keyword_selection"),
            "rotation_strategy": row.get("rotation_strategy"),
        }
        append_ingest_run(log_row)
        if not row.get("skipped"):
            any_ran = True

    if not any_ran:
        print("\nNo jobs ran.", file=sys.stderr)
        if any(j.platform == "x" for j in jobs):
            print("Add GitHub secrets AUTH_TOKEN and CT0, or check daily budget.", file=sys.stderr)
        return 1

    if export:
        subprocess = __import__("subprocess")
        subprocess.run(
            [sys.executable, "scripts/export_dashboard_data.py"],
            cwd=ROOT,
            check=True,
            env={
                **__import__("os").environ,
                "DATABASE_URL": f"sqlite+aiosqlite:///{DEFAULT_DB.resolve()}",
                "USE_EMBEDDING_THEMES": __import__("os").environ.get(
                    "USE_EMBEDDING_THEMES", "true"
                ),
                "RESCORE_BEFORE_EXPORT": __import__("os").environ.get(
                    "RESCORE_BEFORE_EXPORT", "true"
                ),
            },
        )

    summary_path = Path(__import__("os").environ.get("GITHUB_STEP_SUMMARY", ""))
    if summary_path:
        lines = ["## Scheduled ingest\n", "```json\n", json.dumps(results, indent=2), "\n```\n"]
        Path(summary_path).write_text("".join(lines), encoding="utf-8")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--no-export", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.config, export=not args.no_export)))


if __name__ == "__main__":
    main()
