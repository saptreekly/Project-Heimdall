from datetime import UTC, datetime, timedelta

from heimdall.analysis.duplicates import (
    SYNC_BURST_MIN_AUTHORS,
    SYNC_BURST_WINDOW_SECONDS,
    apply_duplicate_temporal_cib_boost,
    cluster_timing_metrics,
    find_duplicate_clusters_from_rows,
    max_distinct_authors_in_window,
)


def _t(base: datetime, seconds: float) -> datetime:
    return base + timedelta(seconds=seconds)


def test_max_distinct_authors_in_90s_window() -> None:
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    events = [(_t(base, i * 10), f"author_{i}") for i in range(5)]
    assert max_distinct_authors_in_window(events) == 5


def test_organic_copypasta_spread_over_hours_not_burst() -> None:
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    events = [(_t(base, i * 3600), f"author_{i}") for i in range(5)]
    metrics = cluster_timing_metrics(events)
    assert metrics["burst_synchronized"] is False
    assert metrics["burst_author_count"] < SYNC_BURST_MIN_AUTHORS


def test_synchronized_cluster_flags_burst() -> None:
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    text = "RELEASE THE KRAKEN NOW"
    rows = [
        (i + 1, f"u{i}", text, _t(base, i * 15))
        for i in range(SYNC_BURST_MIN_AUTHORS)
    ]
    clusters = find_duplicate_clusters_from_rows(rows)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.burst_synchronized is True
    assert c.burst_author_count >= SYNC_BURST_MIN_AUTHORS
    assert c.cluster_span_seconds <= SYNC_BURST_WINDOW_SECONDS


def test_cib_suspicion_spikes_on_synchronized_burst() -> None:
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    rows = [(i + 1, f"u{i}", "coordinated drop", _t(base, i * 12)) for i in range(5)]
    clusters = find_duplicate_clusters_from_rows(rows)
    suspicion, signals = apply_duplicate_temporal_cib_boost(0.1, [], clusters)
    assert suspicion >= 0.72
    assert any("synchronized_duplicate_burst" in s for s in signals)


def test_cib_unchanged_without_burst() -> None:
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    rows = [
        (1, "u1", "same", _t(base, 0)),
        (2, "u2", "same", _t(base, 7200)),
    ]
    clusters = find_duplicate_clusters_from_rows(rows)
    suspicion, signals = apply_duplicate_temporal_cib_boost(0.15, ["existing"], clusters)
    assert suspicion == 0.15
    assert signals == ["existing"]
