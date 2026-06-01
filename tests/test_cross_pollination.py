from heimdall.analysis.cross_pollination import (
    build_cross_pollination_report,
    cross_pollination_cib_signals,
    narrative_cross_pollination_hits,
    pollination_score,
)


def _row(
    nid: int,
    name: str,
    author: str,
    *,
    platform: str = "x",
    posts: int = 5,
    handle: str | None = None,
) -> tuple:
    return (
        nid,
        name,
        platform,
        author,
        handle or f"@{author}",
        posts,
        0.25,
        "2026-06-01T10:00:00",
        "2026-06-01T12:00:00",
    )


def test_build_cross_pollination_report_multi_narrative_actor() -> None:
    rows = [
        _row(1, "midterms_2026", "actor_1", posts=10),
        _row(2, "border_crisis", "actor_1", posts=8),
        _row(1, "midterms_2026", "solo_actor", posts=3),
    ]
    report = build_cross_pollination_report(rows, min_narratives=2)
    assert report["actor_count"] == 1
    actor = report["actors"][0]
    assert actor["author_id"] == "actor_1"
    assert actor["narrative_count"] == 2
    assert report["narrative_pairs"][0]["shared_actor_count"] == 1


def test_solo_narrative_author_excluded() -> None:
    rows = [_row(1, "only", "loner")]
    report = build_cross_pollination_report(rows)
    assert report["actor_count"] == 0


def test_narrative_hits_for_current_silo() -> None:
    rows = [
        _row(1, "midterms_2026", "actor_1"),
        _row(2, "flashpoint_b", "actor_1"),
        _row(3, "flashpoint_c", "actor_1"),
    ]
    report = build_cross_pollination_report(rows)
    hits = narrative_cross_pollination_hits(report, 1)
    assert hits["hit_count"] == 1
    assert hits["actors"][0]["other_narrative_count"] == 2


def test_pollination_score_increases_with_span() -> None:
    low = pollination_score(2, 10, 0.0)
    high = pollination_score(3, 20, 14.0)
    assert high > low


def test_cross_pollination_cib_signals() -> None:
    rows = [
        _row(1, "n1", "a1"),
        _row(2, "n2", "a1"),
        _row(1, "n1", "a2"),
        _row(2, "n2", "a2"),
    ]
    report = build_cross_pollination_report(rows)
    signals = cross_pollination_cib_signals(report, 1)
    assert any("cross_pollination" in s for s in signals)
