"""Tests for coordination watchlist tier logic."""

from scripts.coordination_watchlist import (
    evaluate_crossings,
    tier_for_score,
)


def test_tier_thresholds() -> None:
    assert tier_for_score(0.0) == "none"
    assert tier_for_score(0.37) == "none"
    assert tier_for_score(0.38) == "watch"
    assert tier_for_score(0.54) == "watch"
    assert tier_for_score(0.55) == "elevated"
    assert tier_for_score(0.64) == "elevated"
    assert tier_for_score(0.65) == "critical"


def test_evaluate_crossings_detects_upgrade() -> None:
    snapshot = {
        "generated_at": "2026-06-01T00:00:00+00:00",
        "narratives": [{"id": 1, "name": "midterms_2026"}],
        "by_narrative_id": {
            "1": {"cib": {"text_coordination_score": 0.55, "suspicion_score": 0.55, "text_signals": ["x"]}}
        },
    }
    state = {"midterms_2026": {"tier": "watch", "text_coordination": 0.4}}
    crossings, new_state = evaluate_crossings(snapshot, state)
    assert len(crossings) == 1
    assert crossings[0].new_tier == "elevated"
    assert new_state["midterms_2026"]["tier"] == "elevated"
