from heimdall.graph.author_signals import enrich_author_bot_signals


def test_high_velocity_author_flagged() -> None:
    author_map = {
        "a1": {"author_id": "a1", "post_count": 4},
    }
    post_rows = [
        {"author_id": "a1", "posted_at": "2026-01-01T10:00:00+00:00"},
        {"author_id": "a1", "posted_at": "2026-01-01T10:10:00+00:00"},
        {"author_id": "a1", "posted_at": "2026-01-01T10:20:00+00:00"},
        {"author_id": "a1", "posted_at": "2026-01-01T10:30:00+00:00"},
    ]
    enrich_author_bot_signals(author_map, post_rows)
    assert author_map["a1"]["high_velocity"] is True
    assert author_map["a1"]["posts_per_hour"] >= 4.0


def test_low_volume_author_not_flagged() -> None:
    author_map = {
        "a2": {"author_id": "a2", "post_count": 2},
    }
    post_rows = [
        {"author_id": "a2", "posted_at": "2026-01-01T10:00:00+00:00"},
        {"author_id": "a2", "posted_at": "2026-01-01T12:00:00+00:00"},
    ]
    enrich_author_bot_signals(author_map, post_rows)
    assert author_map["a2"]["high_velocity"] is False
