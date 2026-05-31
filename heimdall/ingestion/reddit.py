import asyncio
import json
from datetime import datetime, timezone

import praw

from heimdall.config import get_settings
from heimdall.db.models import Platform
from heimdall.ingestion.base import PlatformIngester
from heimdall.ingestion.schemas import RawPost
from heimdall.ingestion.text_clean import clean_post_text


class RedditIngester(PlatformIngester):
    def __init__(self) -> None:
        settings = get_settings()
        self._reddit = praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )

    async def fetch_by_keywords(self, keywords: list[str], limit: int = 50) -> list[RawPost]:
        query = " OR ".join(keywords)
        return await asyncio.to_thread(self._search_sync, query, limit)

    def _search_sync(self, query: str, limit: int) -> list[RawPost]:
        posts: list[RawPost] = []
        for submission in self._reddit.subreddit("all").search(query, limit=limit, sort="new"):
            created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
            text = clean_post_text(f"{submission.title}\n\n{submission.selftext or ''}")
            posts.append(
                RawPost(
                    platform=Platform.REDDIT,
                    external_id=submission.id,
                    author_id=str(submission.author) if submission.author else "deleted",
                    author_handle=str(submission.author) if submission.author else None,
                    text=text,
                    posted_at=created,
                    raw_json=json.dumps(
                        {
                            "subreddit": submission.subreddit.display_name,
                            "score": submission.score,
                            "num_comments": submission.num_comments,
                        }
                    ),
                )
            )
        return posts
