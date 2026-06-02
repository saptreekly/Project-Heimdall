"""Tests for automatic keyword rotation."""

from scripts.keyword_audit import KeywordAuditReport, KeywordStats, SuggestedKeyword
from scripts.rotate_keywords import (
    build_rotation_plan,
    pick_additions,
    identify_stale,
)


def test_identify_stale_respects_pins_and_floor() -> None:
    stats = [
        KeywordStats("2026 midterms", runs=10, inserted=20, fetched=30),
        KeywordStats("2026 red wave", runs=5, inserted=0, fetched=0),
        KeywordStats("2026 midterm fraud", runs=4, inserted=0, fetched=0),
    ]
    removed = identify_stale(
        stats,
        pinned={"2026 midterms"},
        current_keywords=["2026 midterms", "2026 red wave", "2026 midterm fraud"],
        min_keywords=2,
    )
    assert "2026 midterms" not in removed
    assert "2026 red wave" in removed
    assert len(removed) <= 1  # keep at least 2 keywords


def test_pick_additions_skips_similar() -> None:
    added = pick_additions(
        [
            SuggestedKeyword("2026 midterms fraud", "theme", 1.0, "x"),
            SuggestedKeyword("2026 deportations", "theme", 2.0, "y"),
        ],
        current_after_removals=["2026 midterms"],
        max_keywords=5,
    )
    assert "2026 deportations" in added
    assert "2026 midterms fraud" not in added


def test_build_rotation_plan_swaps_stale_for_suggestions() -> None:
    report = KeywordAuditReport(
        window_days=7,
        configured_keywords=["2026 midterms", "2026 red wave", "2026 midterm fraud"],
        stats=[
            KeywordStats("2026 midterms", runs=10, inserted=15, fetched=20),
            KeywordStats("2026 red wave", runs=6, inserted=0, fetched=0),
            KeywordStats("2026 midterm fraud", runs=5, inserted=1, fetched=2),
        ],
        dead_keywords=["2026 red wave"],
        suggestions=[
            SuggestedKeyword("2026 deportations", "theme", 3.0, "gap"),
        ],
    )
    plan = build_rotation_plan(
        report,
        narrative="midterms_2026",
        current_keywords=["2026 midterms", "2026 red wave", "2026 midterm fraud"],
        pinned=("2026 midterms",),
        min_keywords=2,
        max_keywords=5,
        min_runs_before_swap=3,
        ingest_run_count=10,
    )
    assert plan.changed
    assert "2026 midterms" in plan.after
    assert "2026 red wave" not in plan.after
    assert "2026 deportations" in plan.after


def test_build_rotation_plan_skips_without_enough_runs() -> None:
    report = KeywordAuditReport(window_days=7, dead_keywords=["2026 red wave"])
    plan = build_rotation_plan(
        report,
        narrative="midterms_2026",
        current_keywords=["2026 midterms", "2026 red wave"],
        pinned=("2026 midterms",),
        min_keywords=2,
        max_keywords=5,
        min_runs_before_swap=5,
        ingest_run_count=2,
    )
    assert not plan.changed
    assert plan.before == plan.after
