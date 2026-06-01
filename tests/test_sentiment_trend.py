import pytest

from heimdall.analysis.sentiment_shift import build_daily_series, classify_trend


def _series(means: list[float]) -> list[dict]:
    return [
        {"date": f"2026-01-{i + 1:02d}", "mean_outrage": m, "count": 5}
        for i, m in enumerate(means)
    ]


def test_insufficient_data_with_few_buckets() -> None:
    assert classify_trend(_series([0.2])) == "insufficient_data"
    assert classify_trend(_series([0.2, 0.8])) == "insufficient_data"


def test_clear_escalation_over_many_days() -> None:
    assert classify_trend(_series([0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4])) == "escalating"


def test_last_day_outlier_does_not_force_escalation() -> None:
    # Endpoint comparison would mark escalating; regression on smoothed series should not.
    assert classify_trend(_series([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.85])) == "stable"


def test_first_day_outlier_does_not_force_declining_label_as_escalating() -> None:
    assert classify_trend(_series([0.85, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])) == "stable"


def test_noisy_flat_series_is_stable() -> None:
    assert classify_trend(_series([0.4, 0.42, 0.38, 0.41, 0.39, 0.4])) == "stable"


def test_declining_trajectory() -> None:
    assert classify_trend(_series([0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2])) == "declining"


def test_build_daily_series_aggregates_by_date() -> None:
    from datetime import datetime, timezone

    pairs = [
        (datetime(2026, 1, 1, 12, tzinfo=timezone.utc), 0.2),
        (datetime(2026, 1, 1, 18, tzinfo=timezone.utc), 0.4),
        (datetime(2026, 1, 2, 9, tzinfo=timezone.utc), 0.6),
    ]
    series = build_daily_series(pairs)
    assert len(series) == 2
    assert series[0]["date"] == "2026-01-01"
    assert series[0]["mean_outrage"] == 0.3
    assert series[0]["count"] == 2
