import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from heimdall.analysis.duplicates import find_duplicate_clusters_from_rows
from heimdall.api.schemas import (
    AstroturfImportResponse,
    CIBResponse,
    DuplicateClusterOut,
    IngestRequest,
    IngestResponse,
    NarrativeCreate,
    NarrativeSummary,
    Neo4jSyncResponse,
    PostOut,
)
from heimdall.config import get_settings
from heimdall.datasets.astroturf import count_known_bots, import_astroturf, narrative_bot_overlap
from heimdall.datasets.tweet_eval import ALL_SUBSETS, RAGEBAIT_SUBSETS, parse_tweet_eval_meta
from heimdall.nlp.calibrate import tweet_eval_calibration
from heimdall.nlp.outrage import OutrageAnalyzer
from heimdall.db.models import Narrative, OutrageScore, Platform, Post
from heimdall.db.session import get_db
from heimdall.graph.export import build_graph_export
from heimdall.graph.neo4j_sync import Neo4jGraphSync
from heimdall.graph.networkx_analysis import NarrativeGraphAnalyzer
from heimdall.ingestion.pipeline import IngestionPipeline
from heimdall.ingestion.x_guard import (
    XDailyBudgetExceeded,
    XIngestDisabled,
    plan_x_ingest,
)

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "heimdall"}


@router.get("/narratives", response_model=list[NarrativeSummary])
async def list_narratives(db: AsyncSession = Depends(get_db)) -> list[NarrativeSummary]:
    result = await db.execute(
        select(
            Narrative.id,
            Narrative.name,
            Narrative.keywords,
            func.count(Post.id).label("post_count"),
        )
        .outerjoin(Post, Post.narrative_id == Narrative.id)
        .group_by(Narrative.id, Narrative.name, Narrative.keywords)
        .order_by(Narrative.id)
    )
    return [
        NarrativeSummary(
            id=row.id,
            name=row.name,
            keywords=row.keywords,
            post_count=row.post_count,
        )
        for row in result.all()
    ]


@router.post("/narratives", response_model=dict)
async def create_narrative(body: NarrativeCreate, db: AsyncSession = Depends(get_db)) -> dict:
    pipeline = IngestionPipeline(db)
    narrative = await pipeline.ensure_narrative(body.name, body.keywords)
    await db.commit()
    return {"id": narrative.id, "name": narrative.name, "keywords": body.keywords}


def _parse_platform(name: str | None) -> Platform | None:
    if not name:
        return None
    try:
        return Platform(name.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown platform '{name}'. Use: hackernews, mastodon, mock, reddit, tweet_eval, x",
        ) from exc


@router.post("/ingest", response_model=IngestResponse)
async def ingest(body: IngestRequest, db: AsyncSession = Depends(get_db)) -> IngestResponse:
    platform = _parse_platform(body.platform)
    x_plan = None
    keywords = body.keywords
    limit = body.limit

    if platform == Platform.X:
        try:
            x_plan = plan_x_ingest(keywords, limit)
        except XIngestDisabled as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        keywords = x_plan.keywords
        limit = x_plan.limit

    try:
        pipeline = IngestionPipeline(db, platform=platform, x_plan=x_plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = await pipeline.ingest_narrative(
            body.narrative_name,
            keywords,
            limit=limit,
        )
    except XDailyBudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (RuntimeError, httpx.HTTPStatusError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return IngestResponse(**result)


@router.get("/platforms/x/usage")
async def x_usage() -> dict:
    from heimdall.ingestion.x_guard import daily_usage_snapshot

    usage = await daily_usage_snapshot()
    settings = get_settings()
    return {
        **usage,
        "limits": {
            "max_keywords_per_ingest": settings.x_max_keywords_per_ingest,
            "max_posts_per_ingest": settings.x_max_posts_per_ingest,
            "max_tweets_per_search": settings.x_max_tweets_per_search,
            "min_seconds_between_searches": settings.x_min_seconds_between_searches,
            "max_graphql_requests_per_day": settings.x_max_graphql_requests_per_day,
            "ingest_enabled": settings.x_ingest_enabled,
        },
    }


@router.get("/narratives/{narrative_id}/posts", response_model=list[PostOut])
async def list_posts(
    narrative_id: int,
    min_outrage: float | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PostOut]:
    q = (
        select(Post)
        .where(Post.narrative_id == narrative_id)
        .options(joinedload(Post.scores))
        .order_by(Post.posted_at.desc())
        .limit(100)
    )
    result = await db.execute(q)
    posts = result.unique().scalars().all()
    out: list[PostOut] = []
    for p in posts:
        score = p.scores[0] if p.scores else None
        if min_outrage is not None and (not score or score.outrage_index < min_outrage):
            continue
        meta = parse_tweet_eval_meta(p.raw_json)
        out.append(
            PostOut(
                id=p.id,
                platform=p.platform.value,
                author_id=p.author_id,
                text=p.text,
                posted_at=p.posted_at,
                outrage_index=score.outrage_index if score else None,
                sentiment_label=score.sentiment_label if score else None,
                benchmark_label=meta.get("label_name") if meta else None,
            )
        )
    return out


@router.get("/narratives/{narrative_id}/amplification")
async def narrative_amplification(
    narrative_id: int,
    min_posts: int = 2,
    db: AsyncSession = Depends(get_db),
) -> dict:
    exists = await db.execute(select(Narrative.id).where(Narrative.id == narrative_id))
    if not exists.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Narrative not found")

    result = await db.execute(
        select(Post.id, Post.author_id, Post.text).where(Post.narrative_id == narrative_id)
    )
    rows = [(r[0], r[1], r[2]) for r in result.all()]
    clusters = find_duplicate_clusters_from_rows(rows, min_posts=min_posts)
    return {
        "narrative_id": narrative_id,
        "cluster_count": len(clusters),
        "clusters": [
            DuplicateClusterOut(
                count=c.count,
                author_count=len(c.author_ids),
                author_ids=c.author_ids,
                post_ids=c.post_ids,
                sample_text=c.sample_text,
            )
            for c in clusters
        ],
    }


@router.get("/narratives/{narrative_id}/cib", response_model=CIBResponse)
async def analyze_cib(narrative_id: int, db: AsyncSession = Depends(get_db)) -> CIBResponse:
    exists = await db.execute(select(Narrative.id).where(Narrative.id == narrative_id))
    if not exists.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Narrative not found")

    analyzer = NarrativeGraphAnalyzer()
    assessment = await analyzer.assess_narrative(db, narrative_id)
    m = assessment.metrics
    bot_overlap = await narrative_bot_overlap(db, narrative_id)
    return CIBResponse(
        narrative_id=narrative_id,
        suspicion_score=assessment.suspicion_score,
        organic_score=m.organic_score,
        signals=assessment.signals,
        node_count=m.node_count,
        edge_count=m.edge_count,
        density=m.density,
        top_amplifiers=m.top_amplifiers,
        coordinated_clusters=m.coordinated_clusters,
        iu_astroturf=bot_overlap,
    )


@router.post("/datasets/astroturf/import", response_model=AstroturfImportResponse)
async def astroturf_import(db: AsyncSession = Depends(get_db)) -> AstroturfImportResponse:
    try:
        result = await import_astroturf(db)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AstroturfImportResponse(**result)


@router.get("/datasets/tweet_eval/subsets")
async def tweet_eval_subsets() -> dict:
    return {
        "dataset": "cardiffnlp/tweet_eval",
        "ragebait_subsets": sorted(RAGEBAIT_SUBSETS),
        "all_subsets": sorted(ALL_SUBSETS),
        "usage": {
            "ingest": {
                "platform": "tweet_eval",
                "keywords": ["hate", "offensive"],
                "limit": 100,
            },
            "note": "keywords select HF config subsets; default is hate if unknown.",
        },
    }


@router.post("/narratives/{narrative_id}/rescore")
async def rescore_narrative(narrative_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    exists = await db.execute(select(Narrative.id).where(Narrative.id == narrative_id))
    if not exists.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Narrative not found")
    return await OutrageAnalyzer().rescore_narrative(db, narrative_id)


@router.get("/narratives/{narrative_id}/calibration")
async def outrage_calibration(narrative_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    return await tweet_eval_calibration(db, narrative_id)


@router.get("/datasets/astroturf/stats")
async def astroturf_stats(db: AsyncSession = Depends(get_db)) -> dict:
    total = await count_known_bots(db)
    return {
        "total_known_bots": total,
        "platform": "x",
        "source": "iu_astroturf",
        "tsv_default": "data/astroturf.tsv",
    }


@router.post("/narratives/{narrative_id}/graph/neo4j", response_model=Neo4jSyncResponse)
async def sync_neo4j(
    narrative_id: int,
    include_cib: bool = True,
    db: AsyncSession = Depends(get_db),
) -> Neo4jSyncResponse:
    try:
        payload = await build_graph_export(db, narrative_id, include_cib=include_cib)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    syncer = Neo4jGraphSync()
    try:
        if not await syncer.ping():
            raise HTTPException(
                status_code=503,
                detail="Neo4j is not reachable. Run: docker compose up -d",
            )
        result = await syncer.sync_narrative(payload)
    finally:
        await syncer.close()

    return Neo4jSyncResponse(cib=payload.cib, **result)


@router.get("/narratives/{narrative_id}/sentiment-shift")
async def sentiment_shift(narrative_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Track mean outrage over time buckets to detect escalation."""
    result = await db.execute(
        select(Post.posted_at, OutrageScore.outrage_index, OutrageScore.sentiment_label)
        .join(OutrageScore, OutrageScore.post_id == Post.id)
        .where(Post.narrative_id == narrative_id)
        .order_by(Post.posted_at)
    )
    rows = result.all()
    if not rows:
        return {"narrative_id": narrative_id, "buckets": [], "trend": "insufficient_data"}

    buckets: dict[str, list[float]] = {}
    for posted_at, outrage, _ in rows:
        key = posted_at.strftime("%Y-%m-%d")
        buckets.setdefault(key, []).append(outrage)

    series = [
        {"date": k, "mean_outrage": round(sum(v) / len(v), 4), "count": len(v)}
        for k, v in sorted(buckets.items())
    ]
    if len(series) >= 2:
        trend = "escalating" if series[-1]["mean_outrage"] > series[0]["mean_outrage"] else "stable"
    else:
        trend = "insufficient_data"

    return {"narrative_id": narrative_id, "buckets": series, "trend": trend}
