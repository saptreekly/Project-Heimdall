from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from heimdall.api.schemas import (
    AstroturfImportResponse,
    CIBResponse,
    IngestRequest,
    IngestResponse,
    NarrativeCreate,
    Neo4jSyncResponse,
    PostOut,
)
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

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "heimdall"}


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
            detail=f"Unknown platform '{name}'. Use: hackernews, mastodon, mock, reddit, tweet_eval",
        ) from exc


@router.post("/ingest", response_model=IngestResponse)
async def ingest(body: IngestRequest, db: AsyncSession = Depends(get_db)) -> IngestResponse:
    try:
        pipeline = IngestionPipeline(db, platform=_parse_platform(body.platform))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = await pipeline.ingest_narrative(
        body.narrative_name,
        body.keywords,
        limit=body.limit,
    )
    return IngestResponse(**result)


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
