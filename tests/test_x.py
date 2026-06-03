import json
from pathlib import Path

from heimdall.ingestion.x import _raw_posts_from_tweet
from heimdall.ingestion.x_client import parse_search_timeline, parse_search_timeline_page, parse_tweet_result
from heimdall.db.models import InteractionType, Platform

FIXTURE = Path(__file__).parent / "fixtures" / "x_search_timeline.json"


def test_parse_search_timeline_fixture() -> None:
    payload = json.loads(FIXTURE.read_text())
    tweets = parse_search_timeline(payload)
    assert len(tweets) == 1
    assert tweets[0].tweet_id == "1001"
    assert tweets[0].author_id == "42"
    assert tweets[0].screen_name == "alice"
    assert "border crisis" in tweets[0].text


def test_parse_search_timeline_page_extracts_bottom_cursor() -> None:
    payload = {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [
                            {
                                "entries": [
                                    {
                                        "entryId": "cursor-bottom-abc",
                                        "content": {
                                            "entryType": "TimelineTimelineCursor",
                                            "cursorType": "Bottom",
                                            "value": "cursor-token-123",
                                        },
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }
    }
    tweets, cursor = parse_search_timeline_page(payload)
    assert tweets == []
    assert cursor == "cursor-token-123"


def test_raw_post_platform_x() -> None:
    payload = json.loads(FIXTURE.read_text())
    parsed = parse_search_timeline(payload)[0]
    posts = _raw_posts_from_tweet(parsed)
    assert len(posts) == 1
    post = posts[0]
    assert post.platform == Platform.X
    assert post.external_id == "1001"
    assert post.author_id == "42"
    assert post.author_handle == "@alice"


def test_parse_retweet_adds_share_edge() -> None:
    result = {
        "rest_id": "2002",
        "core": {
            "user_results": {
                "result": {
                    "rest_id": "99",
                    "legacy": {"id_str": "99", "screen_name": "booster"},
                    "core": {"screen_name": "booster"},
                }
            }
        },
        "legacy": {
            "id_str": "2002",
            "created_at": "Mon Jun 01 12:00:00 +0000 2026",
            "retweeted_status_result": {
                "result": {
                    "rest_id": "1001",
                    "core": {
                        "user_results": {
                            "result": {
                                "rest_id": "42",
                                "legacy": {"id_str": "42", "screen_name": "alice"},
                                "core": {"screen_name": "alice"},
                            }
                        }
                    },
                    "legacy": {
                        "id_str": "1001",
                        "full_text": "original outrage text",
                        "created_at": "Mon Jun 01 11:00:00 +0000 2026",
                    },
                }
            },
        },
    }
    parsed = parse_tweet_result(result)
    assert parsed is not None
    assert parsed.is_retweet
    posts = _raw_posts_from_tweet(parsed)
    assert posts[0].interactions[0].interaction_type == InteractionType.SHARE
    assert posts[0].interactions[0].target_author_id == "42"
    assert posts[0].interactions[0].target_external_id == "1001"


def test_parse_reply_adds_reply_edge() -> None:
    result = {
        "rest_id": "3003",
        "core": {
            "user_results": {
                "result": {
                    "rest_id": "77",
                    "legacy": {"id_str": "77", "screen_name": "replier"},
                    "core": {"screen_name": "replier"},
                }
            }
        },
        "legacy": {
            "id_str": "3003",
            "full_text": "replying to your take",
            "created_at": "Mon Jun 01 13:00:00 +0000 2026",
            "in_reply_to_status_id_str": "1001",
            "in_reply_to_user_id_str": "42",
        },
    }
    parsed = parse_tweet_result(result)
    assert parsed is not None
    assert parsed.is_reply
    posts = _raw_posts_from_tweet(parsed)
    types = [i.interaction_type for i in posts[0].interactions]
    assert InteractionType.REPLY in types
    reply = next(i for i in posts[0].interactions if i.interaction_type == InteractionType.REPLY)
    assert reply.target_author_id == "42"
    assert reply.target_external_id == "1001"


def test_parse_quote_adds_quote_edge() -> None:
    result = {
        "rest_id": "4004",
        "core": {
            "user_results": {
                "result": {
                    "rest_id": "88",
                    "legacy": {"id_str": "88", "screen_name": "quoter"},
                    "core": {"screen_name": "quoter"},
                }
            }
        },
        "legacy": {
            "id_str": "4004",
            "full_text": "commentary on this",
            "created_at": "Mon Jun 01 14:00:00 +0000 2026",
            "quoted_status_result": {
                "result": {
                    "rest_id": "1001",
                    "core": {
                        "user_results": {
                            "result": {
                                "rest_id": "42",
                                "legacy": {"id_str": "42", "screen_name": "alice"},
                                "core": {"screen_name": "alice"},
                            }
                        }
                    },
                    "legacy": {
                        "id_str": "1001",
                        "full_text": "quoted original",
                        "created_at": "Mon Jun 01 11:00:00 +0000 2026",
                    },
                }
            },
        },
    }
    parsed = parse_tweet_result(result)
    assert parsed is not None
    assert parsed.is_quote
    posts = _raw_posts_from_tweet(parsed)
    types = [i.interaction_type for i in posts[0].interactions]
    assert InteractionType.QUOTE in types
    quote = next(i for i in posts[0].interactions if i.interaction_type == InteractionType.QUOTE)
    assert quote.target_author_id == "42"
    assert quote.target_external_id == "1001"
