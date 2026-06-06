"""Heuristic bot-amplification signals derived from posting behavior."""

from __future__ import annotations

from datetime import datetime

# Authors with ≥3 posts and this many posts/hour are flagged high-velocity.
HIGH_VELOCITY_POSTS_PER_HOUR = 4.0
HIGH_VELOCITY_MIN_POSTS = 3


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def enrich_author_bot_signals(
    author_map: dict[str, dict],
    post_rows: list[dict],
) -> None:
    """Add posting velocity and activity span fields to author nodes in-place."""
    times_by_author: dict[str, list[datetime]] = {}
    for row in post_rows:
        author_id = row.get("author_id")
        posted_at = _parse_iso(row.get("posted_at"))
        if not author_id or not posted_at:
            continue
        times_by_author.setdefault(str(author_id), []).append(posted_at)

    for author_id, author in author_map.items():
        times = sorted(times_by_author.get(author_id, []))
        if not times:
            author.setdefault("posts_per_hour", 0.0)
            author.setdefault("active_span_hours", 0.0)
            author.setdefault("high_velocity", False)
            continue

        first = times[0]
        last = times[-1]
        span_hours = max((last - first).total_seconds() / 3600.0, 1 / 60)
        post_count = len(times)
        posts_per_hour = round(post_count / span_hours, 2)
        high_velocity = (
            post_count >= HIGH_VELOCITY_MIN_POSTS
            and posts_per_hour >= HIGH_VELOCITY_POSTS_PER_HOUR
        )

        author["first_post_at"] = first.isoformat()
        author["last_post_at"] = last.isoformat()
        author["active_span_hours"] = round(span_hours, 2)
        author["posts_per_hour"] = posts_per_hour
        author["high_velocity"] = high_velocity
