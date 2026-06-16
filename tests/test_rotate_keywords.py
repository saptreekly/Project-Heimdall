"""Tests for automatic keyword rotation."""

from scripts.keyword_audit import KeywordAuditReport, KeywordStats, SuggestedKeyword
from scripts.rotate_keywords import (
    build_rotation_plan,
    identify_stale,
    pick_additions,
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


def test_identify_stale_protects_lifetime_yield() -> None:
    stats = [
        KeywordStats("2026 red wave", runs=6, inserted=0, fetched=0),
    ]
    lifetime = {
        "2026 red wave": KeywordStats("2026 red wave", runs=44, inserted=174, fetched=500),
    }
    removed = identify_stale(
        stats,
        lifetime_stats=lifetime,
        pinned=set(),
        current_keywords=["2026 midterms", "2026 red wave"],
        min_keywords=2,
    )
    assert "2026 red wave" not in removed


def test_pick_additions_skips_similar() -> None:
    added, rejected = pick_additions(
        [
            SuggestedKeyword("2026 midterms fraud", "theme", 1.0, "x"),
            SuggestedKeyword("2026 deportations", "theme", 2.0, "y"),
            SuggestedKeyword("2026 disaster looms", "theme", 3.0, "z"),
        ],
        current_after_removals=["2026 midterms"],
        max_keywords=5,
    )
    assert "2026 deportations" in added
    assert "2026 midterms fraud" not in added
    assert "2026 disaster looms" not in added
    assert any("disaster looms" in r for r in rejected)


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
        lifetime_stats={
            "2026 red wave": KeywordStats("2026 red wave", runs=6, inserted=0, fetched=0),
            "2026 midterm fraud": KeywordStats("2026 midterm fraud", runs=5, inserted=1, fetched=2),
        },
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


def test_build_rotation_plan_keeps_proven_keywords() -> None:
    report = KeywordAuditReport(
        window_days=7,
        stats=[
            KeywordStats("2026 midterms", runs=10, inserted=20, fetched=30),
            KeywordStats("2026 red wave", runs=8, inserted=0, fetched=10),
            KeywordStats("2026 midterm fraud", runs=7, inserted=0, fetched=5),
        ],
        suggestions=[
            SuggestedKeyword("2026 disaster looms", "theme", 5.0, "bad"),
            SuggestedKeyword("2026 hulhumale phase", "theme", 4.0, "bad"),
        ],
    )
    lifetime = {
        "2026 red wave": KeywordStats("2026 red wave", runs=44, inserted=174, fetched=500),
        "2026 midterm fraud": KeywordStats("2026 midterm fraud", runs=36, inserted=142, fetched=400),
    }
    plan = build_rotation_plan(
        report,
        narrative="midterms_2026",
        current_keywords=["2026 midterms", "2026 red wave", "2026 midterm fraud"],
        pinned=("2026 midterms",),
        min_keywords=3,
        max_keywords=8,
        min_runs_before_swap=3,
        ingest_run_count=20,
        lifetime_stats=lifetime,
    )
    assert not plan.changed
    assert "2026 red wave" in plan.after
    assert "2026 midterm fraud" in plan.after
    assert "2026 disaster looms" not in plan.after
