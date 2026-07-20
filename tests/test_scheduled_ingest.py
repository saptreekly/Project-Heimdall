import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.scheduled_ingest import (
    EXPLORE_MIN_RUNS,
    IngestJob,
    load_jobs,
    rotate_x_keywords,
    rotate_x_search_product,
    select_keywords_explore_yield,
    select_keywords_for_run,
)


def _recent_iso(hours_ago: int = 1) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()



def test_load_scheduled_jobs() -> None:
    config = Path("data/scheduled_ingest.json")
    jobs = load_jobs(config)
    assert len(jobs) >= 1
    midterms = next(j for j in jobs if j.narrative_name == "midterms_2026")
    assert midterms.platform == "x"
    assert midterms.rotation_strategy == "explore_yield"
    assert len(midterms.keywords) <= 8
    assert midterms.limit <= 80


def test_rotate_x_keywords_round_robin(tmp_path, monkeypatch) -> None:
    state = tmp_path / "rotation.json"
    monkeypatch.setenv("X_ROTATION_STATE_PATH", str(state))
    kws = ["alpha", "beta", "gamma"]

    a, _ = rotate_x_keywords(kws, 1)
    b, _ = rotate_x_keywords(kws, 1)
    c, _ = rotate_x_keywords(kws, 1)
    d, _ = rotate_x_keywords(kws, 1)

    assert a == ["alpha"]
    assert b == ["beta"]
    assert c == ["gamma"]
    assert d == ["alpha"]


def test_explore_yield_prefers_under_sampled(tmp_path, monkeypatch) -> None:
    log = tmp_path / "ingest_runs.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps({"at": _recent_iso(3), "keywords": ["alpha"], "inserted": 5}),
                json.dumps({"at": _recent_iso(2), "keywords": ["alpha"], "inserted": 3}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("INGEST_RUNS_PATH", str(log))
    selected, reason = select_keywords_explore_yield(["alpha", "beta", "gamma"], 1)
    assert selected == ["beta"]
    assert reason == "explore_under_sampled"


def test_explore_yield_rotates_top_yield_pool(tmp_path, monkeypatch) -> None:
    lines = []
    for i in range(EXPLORE_MIN_RUNS):
        lines.append(
            json.dumps(
                {
                    "at": _recent_iso(10 + i),
                    "keywords": ["alpha"],
                    "inserted": 10,
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "at": _recent_iso(20 + i),
                    "keywords": ["beta"],
                    "inserted": 1,
                }
            )
        )
        lines.append(
            json.dumps(
                {
                    "at": _recent_iso(30 + i),
                    "keywords": ["gamma"],
                    "inserted": 0,
                }
            )
        )
    log = tmp_path / "ingest_runs.jsonl"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    state = tmp_path / "rotation.json"
    monkeypatch.setenv("INGEST_RUNS_PATH", str(log))
    monkeypatch.setenv("X_ROTATION_STATE_PATH", str(state))
    monkeypatch.setenv("X_SCHEDULED_KEYWORDS_PER_RUN", "1")

    job = IngestJob(
        narrative_name="test",
        platform="x",
        keywords=["alpha", "beta", "gamma"],
        limit=20,
        rotation_strategy="explore_yield",
    )
    first, reason1 = select_keywords_for_run(job)
    second, reason2 = select_keywords_for_run(job)
    assert reason1 == "yield_pool_rotate"
    assert reason2 == "yield_pool_rotate"
    assert first != second
    assert first[0] in {"alpha", "beta", "gamma"}


def test_rotate_x_search_product_alternates(tmp_path, monkeypatch) -> None:
    state = tmp_path / "rotation.json"
    monkeypatch.setenv("X_ROTATION_STATE_PATH", str(state))
    assert rotate_x_search_product() == "Latest"
    assert rotate_x_search_product() == "Top"
    assert rotate_x_search_product() == "Latest"


def test_plan_respects_guardrails_for_scheduled_job() -> None:
    from heimdall.ingestion.x_guard import plan_x_ingest

    jobs = load_jobs(Path("data/scheduled_ingest.json"))
    job = next(j for j in jobs if j.platform == "x")
    plan = plan_x_ingest(job.keywords, job.limit, search_product="Top")
    assert len(plan.keywords) <= 8
    assert plan.limit <= 80
    assert plan.graphql_requests == len(plan.keywords)
    assert plan.search_product == "Top"


@pytest.mark.asyncio
async def test_x_job_skipped_without_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("scripts.scheduled_ingest._x_credentials_present", lambda: False)

    cfg = tmp_path / "jobs.json"
    cfg.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "narrative_name": "test_x",
                        "platform": "x",
                        "keywords": ["2026 midterms"],
                        "limit": 10,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from scripts.scheduled_ingest import run_job

    job = load_jobs(cfg)[0]
    result = await run_job(job)
    assert result.get("skipped") is True


def test_is_skippable_x_error_accepts_graphql_dependency() -> None:
    from heimdall.ingestion.x_client import XGraphQLRequestError
    from scripts.scheduled_ingest import _is_skippable_x_error

    assert _is_skippable_x_error(XGraphQLRequestError("Dependency: Unspecified"))
    assert not _is_skippable_x_error(ValueError("unrelated"))
