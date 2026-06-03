import json
from datetime import datetime, timezone

import httpx

from heimdall.db.models import Platform
from heimdall.ingestion.base import PlatformIngester
from heimdall.ingestion.query_plan import QueryPlan
from heimdall.ingestion.schemas import RawPost
from heimdall.ingestion.text_clean import clean_post_text

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


class HackerNewsIngester(PlatformIngester):
    """Public Algolia HN Search API; no API key or account required."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)

    async def fetch_by_keywords(
        self,
        keywords: list[str],
        limit: int = 50,
        *,
        query_plan: QueryPlan | None = None,
    ) -> list[RawPost]:
        if query_plan and query_plan.queries:
            seen: set[str] = set()
            posts: list[RawPost] = []
            for query in query_plan.queries:
                batch = await self._search(query.platform_query, query.max_results)
                for post in batch:
                    if post.external_id in seen:
                        continue
                    seen.add(post.external_id)
                    post = RawPost(
                        platform=post.platform,
                        external_id=post.external_id,
                        author_id=post.author_id,
                        author_handle=post.author_handle,
                        text=post.text,
                        posted_at=post.posted_at,
                        raw_json=post.raw_json,
                        source_keyword=query.narrative_keyword,
                    )
                    posts.append(post)
                    if len(posts) >= limit:
                        return posts[:limit]
            return posts
        return await self._search(" ".join(keywords), limit)

    async def _search(self, query: str, limit: int) -> list[RawPost]:
        params = {
            "query": query,
            "tags": "story",
            "hitsPerPage": min(limit, 100),
        }
        response = await self._client.get(HN_SEARCH_URL, params=params)
        response.raise_for_status()
        hits = response.json().get("hits", [])

        posts: list[RawPost] = []
        for hit in hits:
            object_id = hit.get("objectID") or hit.get("story_id")
            if not object_id:
                continue
            title = hit.get("title") or ""
            story_text = hit.get("story_text") or ""
            text = clean_post_text(f"{title}\n\n{story_text}".strip())
            if not text:
                continue
            author = hit.get("author") or "unknown"
            created = hit.get("created_at_i")
            posted_at = (
                datetime.fromtimestamp(created, tz=timezone.utc)
                if created
                else datetime.now(timezone.utc)
            )
            posts.append(
                RawPost(
                    platform=Platform.HACKERNEWS,
                    external_id=str(object_id),
                    author_id=author,
                    author_handle=f"@{author}",
                    text=text,
                    posted_at=posted_at,
                    raw_json=json.dumps(
                        {
                            "url": hit.get("url"),
                            "points": hit.get("points"),
                            "num_comments": hit.get("num_comments"),
                        }
                    ),
                )
            )
        return posts
