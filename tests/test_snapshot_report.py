"""Tests for scripts/snapshot_report.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.snapshot_report import append_metrics_history, build_report, markdown_report


def test_build_report_minimal_snapshot(tmp_path: Path) -> None:
    snap = {
        "version": 5,
        "generated_at": "2026-06-01T12:00:00+00:00",
        "narratives": [{"id": 1, "name": "test", "post_count": 2}],
        "by_narrative_id": {
            "1": {
                "posts": [{"id": 1}, {"id": 2}],
                "cib": {
                    "text_coordination_score": 0.38,
                    "graph_suspicion_score": 0.0,
                    "suspicion_score": 0.38,
                },
                "themes": {"distinct_theme_count": 2, "emerging_theme_count": 1},
                "provenance": {
                    "posts_total_db": 2,
                    "fuzzy_cluster_count": 1,
                    "duplicate_cluster_count": 0,
                },
            }
        },
        "cross_pollination": {"actor_count": 0},
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snap), encoding="utf-8")

    report = build_report(json.loads(path.read_text()))
    assert report["version"] == 5
    assert report["narrative_count"] == 1
    assert report["total_posts_in_snapshot"] == 2
    assert report["narratives"][0]["text_coordination"] == 0.38

    md = markdown_report(report)
    assert "test" in md
    assert "0.38" in md


def test_append_metrics_history_replaces_same_day(tmp_path: Path) -> None:
    history = tmp_path / "metrics_history.jsonl"
    report = {"version": 5, "total_posts_in_snapshot": 10}
    append_metrics_history(report, history)
    append_metrics_history({**report, "total_posts_in_snapshot": 12}, history)
    lines = [json.loads(line) for line in history.read_text().strip().splitlines()]
    assert len(lines) == 1
    assert lines[0]["total_posts_in_snapshot"] == 12
