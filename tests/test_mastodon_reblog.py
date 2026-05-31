from heimdall.ingestion.mastodon import _posts_from_reblog


def test_reblog_creates_share_edge():
    status = {
        "id": "9001",
        "created_at": "2026-06-01T12:00:00.000Z",
        "account": {"id": "booster", "acct": "booster@mastodon.social"},
        "reblog": {
            "id": "8001",
            "created_at": "2026-06-01T11:00:00.000Z",
            "account": {"id": "original", "acct": "original@mastodon.social"},
            "content": "<p>Immigration policy thread</p>",
        },
    }
    posts = _posts_from_reblog(status, status["reblog"], "immigration", "https://mastodon.social")
    assert len(posts) == 2
    original, boost = posts
    assert original.external_id == "8001"
    assert boost.external_id == "boost-9001"
    assert len(boost.interactions) == 1
    assert boost.interactions[0].target_external_id == "8001"
    assert boost.interactions[0].source_author_id == "booster"
    assert boost.interactions[0].target_author_id == "original"
