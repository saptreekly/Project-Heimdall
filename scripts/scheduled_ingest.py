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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "scheduled_ingest.json"
DEFAULT_DB = ROOT / "data" / "dashboard" / "heimdall.db"
DEFAULT_ROTATION = ROOT / "data" / "dashboard" / "x_keyword_rotation.json"
DEFAULT_INGEST_LOG = ROOT / "data" / "dashboard" / "ingest_runs.jsonl"


@dataclass(frozen=True)
class IngestJob:
    narrative_name: str
    platform: str
    keywords: list[str]
    limit: int


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


def rotate_x_keywords(keywords: list[str], count: int) -> tuple[list[str], int]:
    """
    Pick the next `count` keyword(s) for this cron run (round-robin).

    Used with X_SCHEDULED_KEYWORDS_PER_RUN=1 so 30 daily workflow runs map to
    ~30 GraphQL requests when X_MAX_GRAPHQL_REQUESTS_PER_DAY=30.
    """
    cleaned = [k.strip() for k in keywords if k.strip()]
    if not cleaned or count <= 0:
        return [], 0

    path = _rotation_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state: dict = {"keyword_index": 0}
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {"keyword_index": 0}

    idx = int(state.get("keyword_index", 0)) % len(cleaned)
    selected = [cleaned[(idx + i) % len(cleaned)] for i in range(min(count, len(cleaned)))]
    state["keyword_index"] = idx + len(selected)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return selected, state["keyword_index"]


def keywords_for_scheduled_job(job: IngestJob) -> list[str]:
    per_run = _scheduled_keywords_per_run()
    if per_run is None or job.platform != "x":
        return job.keywords
    rotated, _ = rotate_x_keywords(job.keywords, per_run)
    return rotated or job.keywords


def _ingest_log_path() -> Path:
    raw = os.environ.get("INGEST_RUNS_PATH", "").strip()
    return Path(raw) if raw else DEFAULT_INGEST_LOG


def append_ingest_run(row: dict) -> None:
    """Append one JSON line for keyword audit / rotation reporting."""
    path = _ingest_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at": datetime.now(UTC).isoformat(), **row}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


async def run_job(job: IngestJob) -> dict:
    from heimdall.config import get_settings
    from heimdall.db.models import Platform
    from heimdall.ingestion.pipeline import IngestionPipeline
    from heimdall.ingestion.x_guard import (
        XDailyBudgetExceeded,
        XIngestDisabled,
        daily_usage_snapshot,
        plan_x_ingest,
    )

    settings = get_settings()

    try:
        platform = Platform(job.platform)
    except ValueError as exc:
        raise ValueError(f"Unknown platform '{job.platform}' in job {job.narrative_name}") from exc

    x_plan = None
    if platform == Platform.X:
        if not _x_credentials_present():
            return {
                "narrative_name": job.narrative_name,
                "skipped": True,
                "reason": "AUTH_TOKEN / CT0 not set",
            }
        if not settings.x_ingest_enabled:
            return {
                "narrative_name": job.narrative_name,
                "skipped": True,
                "reason": "X_INGEST_ENABLED=false",
            }
        keywords = keywords_for_scheduled_job(job)
        x_plan = plan_x_ingest(keywords, job.limit)
        usage_before = await daily_usage_snapshot()
        if usage_before["requests_remaining"] < x_plan.graphql_requests:
            return {
                "narrative_name": job.narrative_name,
                "skipped": True,
                "reason": (
                    f"daily GraphQL budget insufficient "
                    f"({usage_before['requests_used_today']}/{usage_before['requests_daily_cap']} used, "
                    f"need {x_plan.graphql_requests})"
                ),
            }

    from heimdall.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        pipeline = IngestionPipeline(db, platform=platform, x_plan=x_plan)
        keywords = x_plan.keywords if x_plan else job.keywords
        limit = x_plan.limit if x_plan else job.limit
        try:
            result = await pipeline.ingest_narrative(
                job.narrative_name,
                keywords,
                limit=limit,
            )
        except (XDailyBudgetExceeded, XIngestDisabled) as exc:
            return {
                "narrative_name": job.narrative_name,
                "skipped": True,
                "reason": str(exc),
            }

    out = {"narrative_name": job.narrative_name, **result}
    if x_plan:
        out["planned_keywords"] = x_plan.keywords
        out["planned_limit"] = x_plan.limit
        out["planned_graphql_requests"] = x_plan.graphql_requests
        out["plan_notes"] = x_plan.notes
        if _scheduled_keywords_per_run() is not None:
            out["scheduled_keyword_rotation"] = True
    return out


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
            "platform": job.platform,
            "keywords": row.get("planned_keywords") or keywords_for_scheduled_job(job),
            "skipped": bool(row.get("skipped")),
            "reason": row.get("reason"),
            "fetched": row.get("fetched"),
            "inserted": row.get("inserted"),
            "scored": row.get("scored"),
            "edges": row.get("edges"),
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
