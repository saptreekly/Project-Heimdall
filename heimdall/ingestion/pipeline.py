from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.config import get_settings
from heimdall.db.models import InteractionEdge, Narrative, Platform, Post
from heimdall.ingestion.base import PlatformIngester
from heimdall.ingestion.hackernews import HackerNewsIngester
from heimdall.ingestion.ingest_filter import should_ingest_post
from heimdall.ingestion.ingest_options import IngestOptions
from heimdall.ingestion.mastodon import MastodonIngester
from heimdall.ingestion.mock import MockIngester
from heimdall.ingestion.query_plan import QueryPlanOptions, build_query_plan
from heimdall.ingestion.rate_limit import TokenBucketRateLimiter
from heimdall.ingestion.reddit import RedditIngester
from heimdall.ingestion.tweet_eval import build_tweet_eval_ingester
from heimdall.ingestion.schemas import RawPost
from heimdall.ingestion.sightings import append_ingest_sighting
from heimdall.ingestion.text_clean import clean_post_text
from heimdall.ingestion.x import XIngester
from heimdall.ingestion.x_guard import XIngestPlan
from heimdall.nlp.outrage import OutrageAnalyzer, build_outrage_analyzer
from heimdall.nlp.post_embeddings import persist_post_embedding


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
        self._platform = platform
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
        self._analyzer = analyzer or build_outrage_analyzer(settings)

    async def ensure_narrative(self, name: str, keywords: list[str]) -> Narrative:
        result = await self._session.execute(select(Narrative).where(Narrative.name == name))
        narrative = result.scalar_one_or_none()
        keyword_csv = ",".join(keywords)
        if narrative:
            if narrative.keywords != keyword_csv:
                narrative.keywords = keyword_csv
            return narrative
        narrative = Narrative(name=name, keywords=keyword_csv)
        self._session.add(narrative)
        await self._session.flush()
        return narrative

    def _resolve_platform(self) -> Platform:
        if self._platform is not None:
            return self._platform
        ingester = self._ingester
        if isinstance(ingester, XIngester):
            return Platform.X
        if isinstance(ingester, HackerNewsIngester):
            return Platform.HACKERNEWS
        if isinstance(ingester, MastodonIngester):
            return Platform.MASTODON
        if isinstance(ingester, RedditIngester):
            return Platform.REDDIT
        return Platform.MOCK

    def _plan_options(self, options: IngestOptions | None) -> QueryPlanOptions:
        opts = options or IngestOptions()
        exclude = opts.x_exclude_terms or QueryPlanOptions().x_exclude_terms
        return QueryPlanOptions(
            x_exclude_terms=exclude,
            x_list_sources=opts.x_list_sources,
            reddit_subreddits=opts.reddit_subreddits or QueryPlanOptions().reddit_subreddits,
        )

    async def preview_ingest(
        self,
        name: str,
        keywords: list[str],
        *,
        limit: int = 50,
        options: IngestOptions | None = None,
    ) -> dict:
        opts = options or IngestOptions(dry_run=True)
        platform = self._resolve_platform()
        plan_opts = self._plan_options(opts)
        query_plan = build_query_plan(platform, keywords, limit, options=plan_opts)
        raw_posts = await self._ingester.fetch_by_keywords(
            keywords,
            limit=limit,
            query_plan=query_plan,
        )
        samples: list[dict] = []
        filtered = 0
        for raw in raw_posts[:20]:
            decision = should_ingest_post(
                clean_post_text(raw.text),
                narrative_keywords=keywords,
                require_keyword_hit=opts.require_keyword_hit,
            )
            if not decision.allow:
                filtered += 1
            samples.append(
                {
                    "external_id": raw.external_id,
                    "source_keyword": raw.source_keyword,
                    "text": clean_post_text(raw.text)[:240],
                    "allow": decision.allow,
                    "filter_reason": decision.reason,
                }
            )
        return {
            "narrative_name": name,
            "platform": platform.value,
            "query_plan": [
                {
                    "narrative_keyword": q.narrative_keyword,
                    "platform_query": q.platform_query,
                    "query_type": q.query_type,
                    "max_results": q.max_results,
                }
                for q in query_plan.queries
            ],
            "fetched": len(raw_posts),
            "filtered_preview": filtered,
            "samples": samples,
        }

    async def ingest_narrative(
        self,
        name: str,
        keywords: list[str],
        *,
        limit: int = 50,
        options: IngestOptions | None = None,
    ) -> dict:
        opts = options or IngestOptions()
        if opts.dry_run:
            return await self.preview_ingest(name, keywords, limit=limit, options=opts)

        await self._limiter.acquire()
        narrative = await self.ensure_narrative(name, keywords)
        platform = self._resolve_platform()
        plan_opts = self._plan_options(opts)
        if opts.query_plan_override is not None:
            query_plan = opts.query_plan_override
        else:
            query_plan = build_query_plan(platform, keywords, limit, options=plan_opts)

        raw_posts = await self._ingester.fetch_by_keywords(
            keywords,
            limit=limit,
            query_plan=query_plan,
        )

        inserted = 0
        updated = 0
        duplicates = 0
        filtered = 0
        scored = 0
        edges = 0
        pages_fetched = 1
        second_page_triggered = False
        keyword_stats: dict[str, dict[str, int]] = {}
        external_to_id: dict[str, int] = {}
        author_discoveries: dict[str, dict] = {}
        interaction_discoveries: list[dict] = []
        latest_post_at: str | None = None
        seen_external_ids: set[str] = set()

        async def process_raw(raw: RawPost) -> None:
            nonlocal inserted, updated, duplicates, filtered, scored, latest_post_at
            seen_external_ids.add(raw.external_id)
            kw = raw.source_keyword or "unknown"
            keyword_stats.setdefault(
                kw,
                {"fetched": 0, "inserted": 0, "updated": 0, "filtered": 0, "duplicates": 0},
            )
            keyword_stats[kw]["fetched"] += 1

            text = clean_post_text(raw.text)
            if opts.apply_ingest_filter:
                decision = should_ingest_post(
                    text,
                    narrative_keywords=keywords,
                    require_keyword_hit=opts.require_keyword_hit,
                )
                if not decision.allow:
                    filtered += 1
                    keyword_stats[kw]["filtered"] += 1
                    return

            action, post_id = await self._upsert_post(narrative.id, raw)
            if post_id is None:
                return
            external_to_id[raw.external_id] = post_id
            posted_iso = raw.posted_at.isoformat()
            if latest_post_at is None or posted_iso > latest_post_at:
                latest_post_at = posted_iso
            via = "author_poll" if kw.startswith("author:") else "keyword"
            depth = 0 if via == "keyword" else 0
            disc = author_discoveries.setdefault(
                raw.author_id,
                {
                    "author_id": raw.author_id,
                    "handle": raw.author_handle,
                    "discovered_via": via,
                    "depth": depth,
                    "inserted": 0,
                },
            )
            if action == "inserted":
                inserted += 1
                keyword_stats[kw]["inserted"] += 1
                disc["inserted"] = int(disc["inserted"]) + 1
                await self._maybe_persist_embedding(post_id, raw.text)
                if await self._analyzer.score_and_persist(self._session, post_id, raw.text):
                    scored += 1
                append_ingest_sighting(
                    {
                        "narrative_name": name,
                        "platform": platform.value,
                        "ingest_keyword": kw,
                        "post_id": post_id,
                        "external_id": raw.external_id,
                        "author_id": raw.author_id,
                        "event": "inserted",
                        "posted_at": posted_iso,
                    }
                )
            elif action == "updated":
                updated += 1
                keyword_stats[kw]["updated"] += 1
                append_ingest_sighting(
                    {
                        "narrative_name": name,
                        "platform": platform.value,
                        "ingest_keyword": kw,
                        "post_id": post_id,
                        "external_id": raw.external_id,
                        "author_id": raw.author_id,
                        "event": "updated",
                        "posted_at": posted_iso,
                    }
                )
            else:
                duplicates += 1
                keyword_stats[kw]["duplicates"] += 1
                append_ingest_sighting(
                    {
                        "narrative_name": name,
                        "platform": platform.value,
                        "ingest_keyword": kw,
                        "post_id": post_id,
                        "external_id": raw.external_id,
                        "author_id": raw.author_id,
                        "event": "duplicate",
                        "posted_at": posted_iso,
                    }
                )

            for interaction in raw.interactions:
                target_id = interaction.target_author_id
                if target_id and target_id != raw.author_id:
                    interaction_discoveries.append(
                        {
                            "author_id": target_id,
                            "handle": None,
                            "discovered_via": interaction.interaction_type.value,
                            "depth": 1,
                            "inserted": 0,
                        }
                    )

        for raw in raw_posts:
            await process_raw(raw)

        eligible = inserted + updated + duplicates
        if (
            isinstance(self._ingester, XIngester)
            and eligible > 0
            and duplicates >= eligible
            and len(raw_posts) > 0
        ):
            plan_limit = self._x_plan.limit if self._x_plan else limit
            remaining = max(plan_limit - len(seen_external_ids), 0)
            extra_posts = await self._ingester.fetch_search_next_page(
                seen=seen_external_ids,
                limit=remaining,
            )
            if extra_posts:
                second_page_triggered = True
                pages_fetched = 2
                raw_posts = [*raw_posts, *extra_posts]
                for raw in extra_posts:
                    await process_raw(raw)

        if opts.backfill_reply_targets and isinstance(self._ingester, XIngester):
            backfill_posts = await self._backfill_reply_targets(
                narrative.id,
                raw_posts,
                external_to_id,
                max_targets=opts.backfill_max_targets,
            )
            for raw in backfill_posts:
                action, post_id = await self._upsert_post(narrative.id, raw)
                if post_id and action == "inserted":
                    inserted += 1
                    external_to_id[raw.external_id] = post_id
                    if await self._analyzer.score_and_persist(self._session, post_id, raw.text):
                        scored += 1

        for raw in raw_posts:
            source_id = external_to_id.get(raw.external_id)
            if not source_id:
                source_id = await self._find_post_id(
                    narrative.id,
                    raw.platform,
                    raw.external_id,
                )
            if not source_id:
                continue
            external_to_id[raw.external_id] = source_id
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

        if inserted > 0 or (self._analyzer.use_embeddings and scored >= 3):
            rescore_result = await self._analyzer.rescore_narrative(self._session, narrative.id)
            scored = rescore_result.get("rescored", scored)

        processed = inserted + updated + duplicates
        duplicate_rate = round(duplicates / max(processed, 1), 3)
        result = {
            "narrative_id": narrative.id,
            "fetched": len(raw_posts),
            "inserted": inserted,
            "net_new": inserted,
            "updated": updated,
            "duplicates": duplicates,
            "re_seen": duplicates,
            "filtered": filtered,
            "processed": processed,
            "duplicate_rate": duplicate_rate,
            "pages_fetched": pages_fetched,
            "second_page_triggered": second_page_triggered,
            "scored": scored,
            "rescored_total": scored,
            "edges": edges,
            "keyword_stats": keyword_stats,
            "query_plan_notes": query_plan.notes + opts.query_plan_notes,
            "author_discoveries": list(author_discoveries.values()) + interaction_discoveries,
            "latest_post_at": latest_post_at,
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
                    "search_product": self._x_plan.search_product,
                }
            result["guardrails"] = guardrails
        return result

    async def _backfill_reply_targets(
        self,
        narrative_id: int,
        raw_posts: list[RawPost],
        external_to_id: dict[str, int],
        *,
        max_targets: int,
    ) -> list[RawPost]:
        missing: list[str] = []
        for raw in raw_posts:
            for interaction in raw.interactions:
                tid = interaction.target_external_id
                if not tid or tid in external_to_id:
                    continue
                existing = await self._find_post_id(narrative_id, raw.platform, tid)
                if existing is None and tid not in missing:
                    missing.append(tid)
        if not missing or not isinstance(self._ingester, XIngester):
            return []
        return await self._ingester.fetch_reply_targets(missing, max_targets=max_targets)

    async def _upsert_post(
        self,
        narrative_id: int,
        raw: RawPost,
    ) -> tuple[str, int | None]:
        text = clean_post_text(raw.text)
        now = datetime.now(timezone.utc)
        existing = await self._session.execute(
            select(Post.id, Post.text).where(
                Post.narrative_id == narrative_id,
                Post.platform == raw.platform,
                Post.external_id == raw.external_id,
            )
        )
        row = existing.first()
        if row:
            post_id, old_text = int(row[0]), str(row[1])
            if old_text != text or raw.source_keyword:
                await self._session.execute(
                    update(Post)
                    .where(Post.id == post_id)
                    .values(
                        text=text,
                        posted_at=raw.posted_at,
                        author_handle=raw.author_handle,
                        raw_json=raw.raw_json,
                        ingest_keyword=raw.source_keyword,
                        last_seen_at=now,
                    )
                )
                return ("updated" if old_text != text else "duplicate"), post_id
            await self._session.execute(
                update(Post).where(Post.id == post_id).values(last_seen_at=now)
            )
            return ("duplicate", post_id)

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
                ingest_keyword=raw.source_keyword,
                last_seen_at=now,
            )
            .returning(Post.id)
        )
        result = await self._session.execute(stmt)
        inserted = result.first()
        if inserted:
            return ("inserted", int(inserted[0]))
        return ("duplicate", None)

    async def _maybe_persist_embedding(self, post_id: int, text: str) -> None:
        settings = get_settings()
        if not settings.use_embedding_themes:
            return
        try:
            await persist_post_embedding(
                self._session,
                post_id,
                clean_post_text(text),
                model_name=settings.embedding_model,
            )
        except Exception:
            return

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
