import json
from pathlib import Path

import pytest

from scripts.scheduled_ingest import load_jobs, rotate_x_keywords


def test_load_scheduled_jobs() -> None:
    config = Path("data/scheduled_ingest.json")
    jobs = load_jobs(config)
    assert len(jobs) >= 1
    midterms = next(j for j in jobs if j.narrative_name == "midterms_2026")
    assert midterms.platform == "x"
    assert len(midterms.keywords) <= 5
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


def test_plan_respects_guardrails_for_scheduled_job() -> None:
    from heimdall.ingestion.x_guard import plan_x_ingest

    jobs = load_jobs(Path("data/scheduled_ingest.json"))
    job = next(j for j in jobs if j.platform == "x")
    plan = plan_x_ingest(job.keywords, job.limit)
    assert len(plan.keywords) <= 5
    assert plan.limit <= 80
    assert plan.graphql_requests == len(plan.keywords)


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
