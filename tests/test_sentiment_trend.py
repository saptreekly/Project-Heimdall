
from heimdall.analysis.sentiment_shift import (
    build_daily_series,
    classify_trend,
    detect_divergence_days,
    week_over_week_shift,
)


def _series(means: list[float]) -> list[dict]:
    return [
        {"date": f"2026-01-{i + 1:02d}", "mean_outrage": m, "count": 5}
        for i, m in enumerate(means)
    ]


def _daily_rows(
    pairs: list[tuple],
) -> list[tuple]:

    rows = []
    for posted_at, outrage in pairs:
        rows.append(
            (
                posted_at,
                outrage,
                "neutral",
                "neutral",
                outrage * 0.5,
                0.0,
                0.0,
                0.0,
                0.0,
            )
        )
    return rows


def test_insufficient_data_with_few_buckets() -> None:
    assert classify_trend(_series([0.2])) == "insufficient_data"
    assert classify_trend(_series([0.2, 0.8])) == "insufficient_data"


def test_clear_escalation_over_many_days() -> None:
    assert classify_trend(_series([0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4])) == "escalating"


def test_last_day_outlier_does_not_force_escalation() -> None:
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
    series = build_daily_series(_daily_rows(pairs))
    assert len(series) == 2
    assert series[0]["date"] == "2026-01-01"
    assert series[0]["mean_outrage"] == 0.3
    assert series[0]["count"] == 2
    assert "tier_counts" in series[0]


def test_detect_divergence_days() -> None:
    series = [
        {"date": "2026-01-01", "count": 2, "mean_outrage": 0.05},
        {"date": "2026-01-02", "count": 20, "mean_outrage": 0.04},
    ]
    divergent = detect_divergence_days(series)
    assert len(divergent) == 1
    assert divergent[0]["date"] == "2026-01-02"


def test_week_over_week_escalation_alert() -> None:
    means = [0.1 + i * 0.01 for i in range(14)]
    series = _series(means)
    wow = week_over_week_shift(series)
    assert wow["available"] is True
    assert wow["alert"] == "escalating_outrage"
