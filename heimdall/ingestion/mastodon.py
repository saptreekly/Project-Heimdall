import json
import re
from datetime import datetime, timezone

import httpx

from heimdall.config import get_settings
from heimdall.db.models import InteractionType, Platform
from heimdall.ingestion.base import PlatformIngester
from heimdall.ingestion.schemas import RawInteraction, RawPost
from heimdall.ingestion.text_clean import clean_post_text

_TAG_RE = re.compile(r"[^a-z0-9_]+", re.I)


class MastodonIngester(PlatformIngester):
    """
    Public hashtag timelines on a Mastodon instance; no token for read-only tag feeds.
    Reblogs in the timeline become SHARE edges to the original author.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base = settings.mastodon_instance_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def fetch_by_keywords(self, keywords: list[str], limit: int = 50) -> list[RawPost]:
        seen: set[str] = set()
        posts: list[RawPost] = []
        per_tag = max(limit // max(len(keywords), 1), 10)

        for keyword in keywords:
            tag = _keyword_to_hashtag(keyword)
            if not tag:
                continue
            batch = await self._fetch_tag(tag, limit=per_tag)
            for post in batch:
                if post.external_id in seen:
                    continue
                seen.add(post.external_id)
                posts.append(post)
                if len(posts) >= limit:
                    return posts[:limit]
        return posts

    async def _fetch_tag(self, tag: str, limit: int) -> list[RawPost]:
        url = f"{self._base}/api/v1/timelines/tag/{tag}"
        response = await self._client.get(url, params={"limit": min(limit, 40)})
        response.raise_for_status()
        statuses = response.json()

        posts: list[RawPost] = []
        for status in statuses:
            reblog = status.get("reblog")
            if reblog:
                posts.extend(_posts_from_reblog(status, reblog, tag, self._base))
            else:
                posts.append(_post_from_status(status, tag, self._base))
        return posts


def _posts_from_reblog(status: dict, reblog: dict, tag: str, base: str) -> list[RawPost]:
    """Original post plus a boost wrapper post that carries the SHARE edge."""
    booster = status.get("account") or {}
    booster_id = str(booster.get("id", "unknown"))
    booster_handle = booster.get("acct") or booster.get("username")
    boost_id = str(status.get("id", ""))
    posted_at = _parse_time(status.get("created_at"))

    original = _post_from_status(reblog, tag, base)
    boost_post = RawPost(
        platform=Platform.MASTODON,
        external_id=f"boost-{boost_id}",
        author_id=booster_id,
        author_handle=f"@{booster_handle}" if booster_handle else None,
        text=clean_post_text(f"boost: {original.text[:200]}"),
        posted_at=posted_at,
        raw_json=json.dumps({"type": "boost", "boosted_id": original.external_id, "tag": tag}),
        interactions=[
            RawInteraction(
                source_author_id=booster_id,
                target_author_id=original.author_id,
                interaction_type=InteractionType.SHARE,
                occurred_at=posted_at,
                target_external_id=original.external_id,
            )
        ],
    )
    return [original, boost_post]


def _post_from_status(status: dict, tag: str, base: str) -> RawPost:
    status_id = str(status.get("id", ""))
    account = status.get("account") or {}
    author_id = str(account.get("id", "unknown"))
    handle = account.get("acct") or account.get("username")
    content = status.get("content") or ""
    text = clean_post_text(_strip_html(content))
    posted_at = _parse_time(status.get("created_at"))
    interactions = _interactions_from_status(status, author_id, posted_at)
    return RawPost(
        platform=Platform.MASTODON,
        external_id=status_id,
        author_id=author_id,
        author_handle=f"@{handle}" if handle else None,
        text=text or "(empty)",
        posted_at=posted_at,
        raw_json=json.dumps(
            {
                "tag": tag,
                "instance": base,
                "reblogs_count": status.get("reblogs_count"),
                "favourites_count": status.get("favourites_count"),
            }
        ),
        interactions=interactions,
    )


def _interactions_from_status(
    status: dict,
    author_id: str,
    posted_at: datetime,
) -> list[RawInteraction]:
    interactions: list[RawInteraction] = []
    reply_to = status.get("in_reply_to_id")
    if reply_to:
        target_author = status.get("in_reply_to_account_id") or "unknown"
        interactions.append(
            RawInteraction(
                source_author_id=author_id,
                target_author_id=str(target_author),
                interaction_type=InteractionType.REPLY,
                occurred_at=posted_at,
                target_external_id=str(reply_to),
            )
        )
    return interactions


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _keyword_to_hashtag(keyword: str) -> str:
    token = keyword.strip().lower().split()[0] if keyword.strip() else ""
    return _TAG_RE.sub("", token)


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "")
