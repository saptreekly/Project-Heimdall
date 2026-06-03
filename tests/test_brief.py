from pathlib import Path

from heimdall.export.brief import build_narrative_brief, scaled_limit, write_brief_artifacts


def test_scaled_limit_grows_with_total() -> None:
    assert scaled_limit(2, floor=3, ceiling=12) == 2
    assert scaled_limit(10, floor=3, ceiling=12) >= 3
    assert scaled_limit(1000, floor=3, ceiling=12) == 12


def test_build_narrative_brief_includes_corpus_and_markdown() -> None:
    brief = build_narrative_brief(
        narrative={"id": 1, "name": "midterms_2026", "post_count": 400},
        bundle={
            "posts": [{}] * 250,
            "cib": {
                "suspicion_score": 0.42,
                "text_coordination_score": 0.31,
                "graph_suspicion_score": 0.1,
                "organic_score": 0.58,
                "node_count": 10,
                "edge_count": 4,
                "signals": ["signal_a"],
            },
            "amplification": {
                "clusters": [
                    {
                        "count": 3,
                        "author_count": 3,
                        "author_ids": ["a", "b", "c"],
                        "post_ids": [1, 2, 3],
                        "sample_text": "duplicate text",
                        "burst_synchronized": False,
                    }
                ]
            },
            "near_duplicates": {"cross_author_fuzzy": []},
            "themes": {
                "distinct_theme_count": 5,
                "clusters": [],
                "timeline": [],
                "sightings": {"total_resightings": 12, "total_net_new": 3},
            },
            "sentiment": {"trend": "rising", "week_over_week": {"alert": "spike"}},
            "provenance": {
                "posts_total_db": 400,
                "posts_in_snapshot": 250,
                "posts_truncated": True,
                "snapshot_post_limit": 250,
                "duplicate_cluster_count": 1,
                "fuzzy_cluster_count": 0,
            },
            "cross_pollination_hits": {"actors": []},
        },
        cross_pollination={"actors": []},
        generated_at="2026-06-03T12:00:00+00:00",
    )
    assert brief["meta"]["posts_total_db"] == 400
    assert brief["meta"]["posts_truncated"] is True
    assert "## Corpus" in brief["markdown"]
    assert "400" in brief["markdown"]
    assert brief["sections"]["exact_duplicates"]


def test_write_brief_artifacts(tmp_path: Path) -> None:
    snapshot = {
        "generated_at": "2026-06-03T12:00:00+00:00",
        "narratives": [{"id": 1, "name": "midterms_2026", "post_count": 10}],
        "by_narrative_id": {
            "1": {
                "posts": [],
                "cib": {"suspicion_score": 0.1, "organic_score": 0.9, "signals": []},
                "amplification": {"clusters": []},
                "near_duplicates": {"cross_author_fuzzy": []},
                "themes": {"clusters": [], "timeline": []},
                "sentiment": {},
                "provenance": {"posts_total_db": 10, "posts_in_snapshot": 10, "posts_truncated": False},
                "cross_pollination_hits": {"actors": []},
            }
        },
        "cross_pollination": {"actors": []},
    }
    paths = write_brief_artifacts(snapshot, tmp_path)
    assert any(p.name == "INDEX.md" for p in paths)
    md = tmp_path / "midterms_2026.md"
    assert md.is_file()
    assert "Heimdall briefing" in md.read_text(encoding="utf-8")
