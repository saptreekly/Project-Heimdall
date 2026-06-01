import json
import uuid
from datetime import datetime, timedelta, timezone

from heimdall.db.models import InteractionType, Platform
from heimdall.ingestion.base import PlatformIngester
from heimdall.ingestion.schemas import RawInteraction, RawPost


class MockIngester(PlatformIngester):
    """Synthetic posts for local dev without API keys."""

    async def fetch_by_keywords(self, keywords: list[str], limit: int = 50) -> list[RawPost]:
        now = datetime.now(timezone.utc)
        posts: list[RawPost] = []
        bot_cluster = ["bot_alpha", "bot_beta", "bot_gamma"]
        organic = ["user_101", "user_202", "user_303", "user_404"]

        templates = [
            "They are destroying our country. {kw} is proof the elites hate you.",
            "Wake up!!! {kw} - share before they delete this!!!",
            "I'm just asking questions about {kw}. Why is no one in the media talking about it?",
            "Normal political disagreement on {kw} - we can disagree without hating each other.",
        ]

        for i in range(min(limit, 20)):
            author = bot_cluster[i % 3] if i < 8 else organic[i % 4]
            kw = keywords[i % len(keywords)] if keywords else "narrative"
            text = templates[i % len(templates)].format(kw=kw)
            post_id = str(uuid.uuid4())
            interactions: list[RawInteraction] = []
            if i > 0 and i < 8:
                interactions.append(
                    RawInteraction(
                        source_author_id=author,
                        target_author_id=bot_cluster[0],
                        interaction_type=InteractionType.SHARE,
                        occurred_at=now - timedelta(minutes=i),
                        target_external_id=posts[0].external_id if posts else None,
                    )
                )
            if i == 9 and posts:
                interactions.append(
                    RawInteraction(
                        source_author_id=author,
                        target_author_id=organic[0],
                        interaction_type=InteractionType.REPLY,
                        occurred_at=now - timedelta(minutes=i),
                        target_external_id=posts[0].external_id,
                    )
                )
            if i == 10 and posts:
                interactions.append(
                    RawInteraction(
                        source_author_id=author,
                        target_author_id=organic[1],
                        interaction_type=InteractionType.QUOTE,
                        occurred_at=now - timedelta(minutes=i),
                        target_external_id=posts[1].external_id if len(posts) > 1 else posts[0].external_id,
                    )
                )
            posts.append(
                RawPost(
                    platform=Platform.MOCK,
                    external_id=post_id,
                    author_id=author,
                    author_handle=f"@{author}",
                    text=text,
                    posted_at=now - timedelta(hours=i),
                    raw_json=json.dumps({"keyword": kw, "synthetic": True}),
                    interactions=interactions,
                )
            )
        return posts
