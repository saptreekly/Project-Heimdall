from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.config import get_settings
from heimdall.db.models import InteractionEdge, Narrative, Platform, Post
from heimdall.ingestion.base import PlatformIngester
from heimdall.ingestion.hackernews import HackerNewsIngester
from heimdall.ingestion.mastodon import MastodonIngester
from heimdall.ingestion.mock import MockIngester
from heimdall.ingestion.rate_limit import TokenBucketRateLimiter
from heimdall.ingestion.reddit import RedditIngester
from heimdall.ingestion.tweet_eval import build_tweet_eval_ingester
from heimdall.ingestion.x import XIngester
from heimdall.ingestion.x_guard import XIngestPlan
from heimdall.ingestion.schemas import RawPost
from heimdall.ingestion.text_clean import clean_post_text
from heimdall.nlp.outrage import OutrageAnalyzer


def _dialect_insert(table):
    url = get_settings().database_url
    if url.startswith("sqlite"):
        return sqlite_insert(table)
    return pg_insert(table)


def build_ingester(platform: Platform | None = None) -> PlatformIngester:
    settings = get_settings()
    if platform == Platform.MOCK:
        return MockIngester()
    if platform == Platform.REDDIT:
        if settings.reddit_client_id and settings.reddit_client_secret:
            return RedditIngester()
        raise ValueError("Reddit credentials missing; use platform=hackernews or mastodon")
    if platform == Platform.HACKERNEWS:
        return HackerNewsIngester()
    if platform == Platform.MASTODON:
        return MastodonIngester()
    if platform == Platform.TWEET_EVAL:
        return build_tweet_eval_ingester()
    if platform == Platform.X:
        return XIngester()
    if platform is None:
        default = settings.default_ingester.lower()
        if default == "mastodon":
            return MastodonIngester()
        if default == "reddit" and settings.reddit_client_id and settings.reddit_client_secret:
            return RedditIngester()
        if default == "mock":
            return MockIngester()
        return HackerNewsIngester()
    return MockIngester()


class IngestionPipeline:
    def __init__(
        self,
        session: AsyncSession,
        ingester: PlatformIngester | None = None,
        analyzer: OutrageAnalyzer | None = None,
        platform: Platform | None = None,
        *,
        x_plan: XIngestPlan | None = None,
    ) -> None:
        settings = get_settings()
        self._session = session
        if ingester is not None:
            self._ingester = ingester
        elif platform == Platform.X and x_plan is not None:
            self._ingester = XIngester(plan=x_plan)
        else:
            self._ingester = build_ingester(platform)
        self._x_plan = x_plan
        self._limiter = TokenBucketRateLimiter(
            settings.ingest_requests_per_minute,
            settings.ingest_burst,
        )
        self._analyzer = analyzer or OutrageAnalyzer(
            use_embeddings=settings.use_embedding_themes,
            embedding_model=settings.embedding_model,
        )

    async def ensure_narrative(self, name: str, keywords: list[str]) -> Narrative:
        result = await self._session.execute(select(Narrative).where(Narrative.name == name))
        narrative = result.scalar_one_or_none()
        if narrative:
            return narrative
        narrative = Narrative(name=name, keywords=",".join(keywords))
        self._session.add(narrative)
        await self._session.flush()
        return narrative

    async def ingest_narrative(
        self,
        name: str,
        keywords: list[str],
        *,
        limit: int = 50,
    ) -> dict:
        await self._limiter.acquire()
        narrative = await self.ensure_narrative(name, keywords)
        raw_posts = await self._ingester.fetch_by_keywords(keywords, limit=limit)

        inserted = 0
        scored = 0
        edges = 0
        external_to_id: dict[str, int] = {}

        for raw in raw_posts:
            post_id = await self._upsert_post(narrative.id, raw)
            if post_id:
                inserted += 1
                external_to_id[raw.external_id] = post_id
                if await self._analyzer.score_and_persist(self._session, post_id, raw.text):
                    scored += 1

        for raw in raw_posts:
            source_id = external_to_id.get(raw.external_id)
            if not source_id:
                continue
            for interaction in raw.interactions:
                target_id = None
                if interaction.target_external_id:
                    target_id = external_to_id.get(interaction.target_external_id)
                    if target_id is None:
                        target_id = await self._find_post_id(
                            narrative.id,
                            raw.platform,
                            interaction.target_external_id,
                        )
                edge = InteractionEdge(
                    narrative_id=narrative.id,
                    source_post_id=source_id,
                    target_post_id=target_id,
                    source_author_id=interaction.source_author_id,
                    target_author_id=interaction.target_author_id,
                    interaction_type=interaction.interaction_type,
                    occurred_at=interaction.occurred_at,
                )
                self._session.add(edge)
                edges += 1

        await self._session.commit()

        if self._analyzer.use_embeddings and scored >= 3:
            rescore_result = await self._analyzer.rescore_narrative(self._session, narrative.id)
            scored = rescore_result.get("rescored", scored)

        result = {
            "narrative_id": narrative.id,
            "fetched": len(raw_posts),
            "inserted": inserted,
            "scored": scored,
            "edges": edges,
        }
        if isinstance(self._ingester, XIngester):
            guardrails: dict = {"notes": list(self._x_plan.notes) if self._x_plan else []}
            if self._ingester.last_usage:
                guardrails["usage"] = self._ingester.last_usage
            if self._x_plan:
                guardrails["plan"] = {
                    "keywords": self._x_plan.keywords,
                    "limit": self._x_plan.limit,
                    "graphql_requests": self._x_plan.graphql_requests,
                }
            result["guardrails"] = guardrails
        return result

    async def _upsert_post(self, narrative_id: int, raw: RawPost) -> int | None:
        text = clean_post_text(raw.text)
        stmt = (
            _dialect_insert(Post)
            .values(
                narrative_id=narrative_id,
                platform=raw.platform,
                external_id=raw.external_id,
                author_id=raw.author_id,
                author_handle=raw.author_handle,
                text=text,
                posted_at=raw.posted_at,
                raw_json=raw.raw_json,
            )
            .on_conflict_do_nothing(
                index_elements=["narrative_id", "platform", "external_id"]
            )
            .returning(Post.id)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row:
            return row[0]
        existing = await self._session.execute(
            select(Post.id).where(
                Post.narrative_id == narrative_id,
                Post.platform == raw.platform,
                Post.external_id == raw.external_id,
            )
        )
        return existing.scalar_one_or_none()

    async def _find_post_id(
        self,
        narrative_id: int,
        platform: Platform,
        external_id: str,
    ) -> int | None:
        result = await self._session.execute(
            select(Post.id).where(
                Post.narrative_id == narrative_id,
                Post.platform == platform,
                Post.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()
