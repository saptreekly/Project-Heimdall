from heimdall.export.coordination_overlay import attach_coordination_overlays, classify_coordination_tier


def test_classify_burst_exact_as_high() -> None:
    tier, label = classify_coordination_tier(
        exact_refs=[{"burst_synchronized": True, "author_count": 4}],
        fuzzy_refs=[],
        unique_author_count=4,
        unique_post_count=6,
        emerging_theme=False,
    )
    assert tier == "high"
    assert label == "Template amplification"


def test_attach_coordination_overlay_links_overlap() -> None:
    themes = [
        {
            "cluster_id": 1,
            "post_ids": [1, 2, 3, 4],
            "emerging_theme": True,
        }
    ]
    amp = [
        {
            "post_ids": [2, 3],
            "count": 2,
            "author_ids": ["a", "b"],
            "author_count": 2,
            "sample_text": "same text",
            "burst_synchronized": False,
        }
    ]
    fuzzy = [
        {
            "post_ids": [3, 4],
            "count": 2,
            "author_ids": ["b", "c"],
            "author_count": 2,
            "sample_text": "near same",
            "burst_synchronized": False,
        }
    ]
    posts = [
        {"id": 1, "author_id": "a"},
        {"id": 2, "author_id": "a"},
        {"id": 3, "author_id": "b"},
        {"id": 4, "author_id": "c"},
    ]
    attach_coordination_overlays(themes, amp, fuzzy, [], posts)
    overlay = themes[0]["coordination"]
    assert overlay["unique_author_count"] == 3
    assert overlay["unique_post_count"] == 4
    assert len(overlay["exact_duplicate_clusters"]) == 1
    assert len(overlay["fuzzy_clusters"]) == 1
    assert overlay["tier"] in ("medium", "high")
