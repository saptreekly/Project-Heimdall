import json
from datetime import datetime, timezone

from heimdall.config import get_settings
from heimdall.db.models import InteractionType, Platform
from heimdall.ingestion.base import PlatformIngester
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

    async def fetch_by_keywords(self, keywords: list[str], limit: int = 50) -> list[RawPost]:
        plan = self._plan or plan_x_ingest(keywords, limit)
        self.last_usage = await reserve_daily_requests(plan.graphql_requests)
        per_search = max_tweets_per_search(plan)

        seen: set[str] = set()
        posts: list[RawPost] = []
        first = True

        for keyword in plan.keywords:
            if not first:
                await wait_between_searches()
            first = False

            token = keyword.strip()
            if token.lower().startswith(_LIST_PREFIX):
                list_id = token[len(_LIST_PREFIX) :].strip()
                batch = await self._client.list_timeline(
                    list_id, count=min(per_search, get_settings().x_max_tweets_per_search)
                )
            else:
                batch = await self._client.search(
                    token,
                    count=min(per_search, get_settings().x_max_tweets_per_search),
                    product="Latest",
                )
            for parsed in batch:
                for raw in _raw_posts_from_tweet(parsed):
                    if raw.external_id in seen:
                        continue
                    seen.add(raw.external_id)
                    posts.append(raw)
                    if len(posts) >= plan.limit:
                        return posts[: plan.limit]
        return posts


def _raw_posts_from_tweet(parsed: ParsedXTweet) -> list[RawPost]:
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

    primary = RawPost(
        platform=Platform.X,
        external_id=parsed.tweet_id,
        author_id=parsed.author_id,
        author_handle=handle,
        text=clean_post_text(parsed.text),
        posted_at=posted_at,
        raw_json=json.dumps(
            {
                "screen_name": parsed.screen_name,
                "is_retweet": parsed.is_retweet,
                "retweet_tweet_id": parsed.retweet_tweet_id,
                "retweet_author_id": parsed.retweet_author_id,
            }
        ),
        interactions=interactions,
    )
    return [primary]
