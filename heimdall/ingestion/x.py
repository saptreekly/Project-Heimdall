import json
from dataclasses import dataclass
from datetime import datetime, timezone

from heimdall.config import get_settings
from heimdall.db.models import InteractionType, Platform
from heimdall.ingestion.base import PlatformIngester
from heimdall.ingestion.query_plan import QueryPlan, SearchQuery
from heimdall.ingestion.schemas import RawInteraction, RawPost
from heimdall.ingestion.text_clean import clean_post_text
from heimdall.ingestion.x_client import ParsedXTweet, XGraphQLClient
from heimdall.ingestion.x_guard import (
    XIngestPlan,
    max_tweets_per_search,
    plan_x_ingest,
    reserve_daily_requests,
    wait_between_searches,
)

_LIST_PREFIX = "list:"


@dataclass
class _PendingSearch:
    platform_query: str
    narrative_keyword: str
    cap: int
    cursor: str | None


class XIngester(PlatformIngester):
    """
    Ingest public X timelines via session cookies (AUTH_TOKEN + CT0).

    Keywords are passed to SearchTimeline (product=Latest). Use ``list:1234567890``
    to pull a list timeline instead of search. Subject to x_guard rate limits.
    """

    def __init__(self, plan: XIngestPlan | None = None) -> None:
        settings = get_settings()
        if not settings.x_auth_token or not settings.x_ct0:
            raise ValueError(
                "X session cookies missing; set X_AUTH_TOKEN and X_CT0 (or AUTH_TOKEN and CT0) in .env"
            )
        self._client = XGraphQLClient(settings.x_auth_token, settings.x_ct0)
        self._plan = plan
        self.last_usage: dict | None = None
        self._pending_search: _PendingSearch | None = None

    async def fetch_by_keywords(
        self,
        keywords: list[str],
        limit: int = 50,
        *,
        query_plan: QueryPlan | None = None,
    ) -> list[RawPost]:
        searches: list[SearchQuery]
        if query_plan:
            searches = query_plan.queries
            gql_count = len(searches)
            plan = self._plan or plan_x_ingest(
                query_plan.keywords,
                min(limit, query_plan.total_limit),
                graphql_requests=gql_count,
            )
        else:
            plan = self._plan or plan_x_ingest(keywords, limit)
            per_search = max_tweets_per_search(plan)
            searches = []
            for keyword in plan.keywords:
                token = keyword.strip()
                qtype = "list" if token.lower().startswith(_LIST_PREFIX) else "search"
                searches.append(SearchQuery(keyword, token, qtype, per_search))

        self.last_usage = await reserve_daily_requests(len(searches))
        seen: set[str] = set()
        posts: list[RawPost] = []
        first = True
        self._pending_search = None

        for query in searches:
            if not first:
                await wait_between_searches()
            first = False

            cap = min(query.max_results, get_settings().x_max_tweets_per_search)
            if query.query_type == "list":
                list_id = query.platform_query[len(_LIST_PREFIX) :].strip()
                batch = await self._client.list_timeline(list_id, count=cap)
            else:
                batch, next_cursor = await self._client.search_page(
                    query.platform_query,
                    count=cap,
                    product="Latest",
                )
                self._pending_search = _PendingSearch(
                    platform_query=query.platform_query,
                    narrative_keyword=query.narrative_keyword,
                    cap=cap,
                    cursor=next_cursor,
                )
            for parsed in batch:
                for raw in _raw_posts_from_tweet(parsed, source_keyword=query.narrative_keyword):
                    if raw.external_id in seen:
                        continue
                    seen.add(raw.external_id)
                    posts.append(raw)
                    if len(posts) >= plan.limit:
                        return posts[: plan.limit]
        return posts

    async def fetch_search_next_page(
        self,
        *,
        seen: set[str],
        limit: int,
    ) -> list[RawPost]:
        pending = self._pending_search
        if not pending or not pending.cursor or limit <= 0:
            return []

        self.last_usage = await reserve_daily_requests(1)
        await wait_between_searches()
        batch, next_cursor = await self._client.search_page(
            pending.platform_query,
            count=pending.cap,
            product="Latest",
            cursor=pending.cursor,
        )
        pending.cursor = next_cursor
        posts: list[RawPost] = []
        for parsed in batch:
            for raw in _raw_posts_from_tweet(parsed, source_keyword=pending.narrative_keyword):
                if raw.external_id in seen:
                    continue
                seen.add(raw.external_id)
                posts.append(raw)
                if len(posts) >= limit:
                    return posts
        return posts

    async def fetch_reply_targets(
        self,
        tweet_ids: list[str],
        *,
        max_targets: int = 5,
    ) -> list[RawPost]:
        seen: set[str] = set()
        posts: list[RawPost] = []
        for tid in tweet_ids[:max_targets]:
            tweets = await self._client.fetch_by_tweet_ids([tid])
            for parsed in tweets:
                for raw in _raw_posts_from_tweet(parsed, source_keyword="reply_backfill"):
                    if raw.external_id in seen:
                        continue
                    seen.add(raw.external_id)
                    posts.append(raw)
        return posts


def _raw_posts_from_tweet(
    parsed: ParsedXTweet,
    *,
    source_keyword: str | None = None,
) -> list[RawPost]:
    posted_at = parsed.created_at or datetime.now(timezone.utc)
    handle = f"@{parsed.screen_name}"
    interactions: list[RawInteraction] = []

    if parsed.is_retweet and parsed.retweet_author_id and parsed.retweet_tweet_id:
        interactions.append(
            RawInteraction(
                source_author_id=parsed.author_id,
                target_author_id=parsed.retweet_author_id,
                interaction_type=InteractionType.SHARE,
                occurred_at=posted_at,
                target_external_id=parsed.retweet_tweet_id,
            )
        )
    elif parsed.is_quote and parsed.quote_author_id and parsed.quote_tweet_id:
        interactions.append(
            RawInteraction(
                source_author_id=parsed.author_id,
                target_author_id=parsed.quote_author_id,
                interaction_type=InteractionType.QUOTE,
                occurred_at=posted_at,
                target_external_id=parsed.quote_tweet_id,
            )
        )

    if parsed.is_reply and parsed.reply_author_id and parsed.reply_tweet_id:
        interactions.append(
            RawInteraction(
                source_author_id=parsed.author_id,
                target_author_id=parsed.reply_author_id,
                interaction_type=InteractionType.REPLY,
                occurred_at=posted_at,
                target_external_id=parsed.reply_tweet_id,
            )
        )

    primary = RawPost(
        platform=Platform.X,
        external_id=parsed.tweet_id,
        author_id=parsed.author_id,
        author_handle=handle,
        text=clean_post_text(parsed.text),
        posted_at=posted_at,
        source_keyword=source_keyword,
        raw_json=json.dumps(
            {
                "screen_name": parsed.screen_name,
                "is_retweet": parsed.is_retweet,
                "retweet_tweet_id": parsed.retweet_tweet_id,
                "retweet_author_id": parsed.retweet_author_id,
                "is_reply": parsed.is_reply,
                "reply_tweet_id": parsed.reply_tweet_id,
                "reply_author_id": parsed.reply_author_id,
                "is_quote": parsed.is_quote,
                "quote_tweet_id": parsed.quote_tweet_id,
                "quote_author_id": parsed.quote_author_id,
            }
        ),
        interactions=interactions,
    )
    return [primary]
