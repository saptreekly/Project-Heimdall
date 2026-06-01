"""Build a JSON snapshot for the static analysis dashboard (GitHub Pages)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from heimdall.analysis.duplicates import find_duplicate_clusters_from_rows
from heimdall.api.schemas import CIBResponse, DuplicateClusterOut, NarrativeSummary, PostOut
from heimdall.datasets.astroturf import narrative_bot_overlap
from heimdall.datasets.tweet_eval import parse_tweet_eval_meta
from heimdall.db.models import Narrative, OutrageScore, Platform, Post
from heimdall.graph.networkx_analysis import NarrativeGraphAnalyzer


async def list_narrative_summaries(db: AsyncSession) -> list[NarrativeSummary]:
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


def _normalize_platform(raw: str) -> str:
    key = (raw or "").strip().lower()
    try:
        return Platform(key).value
    except ValueError:
        return key or "unknown"


async def narrative_posts(db: AsyncSession, narrative_id: int) -> list[PostOut]:
    # Cast platform to string so legacy rows (e.g. MOCK) do not break Enum coercion.
    rows = await db.execute(
        select(
            Post.id,
            cast(Post.platform, String),
            Post.author_id,
            Post.text,
            Post.posted_at,
            Post.raw_json,
        )
        .where(Post.narrative_id == narrative_id)
        .order_by(Post.posted_at.desc())
        .limit(100)
    )
    out: list[PostOut] = []
    for pid, platform_raw, author_id, text, posted_at, raw_json in rows.all():
        score_row = await db.execute(
            select(OutrageScore.outrage_index, OutrageScore.sentiment_label).where(
                OutrageScore.post_id == pid
            )
        )
        score = score_row.first()
        meta = parse_tweet_eval_meta(raw_json)
        out.append(
            PostOut(
                id=pid,
                platform=_normalize_platform(platform_raw),
                author_id=author_id,
                text=text,
                posted_at=posted_at,
                outrage_index=score[0] if score else None,
                sentiment_label=score[1] if score else None,
                benchmark_label=meta.get("label_name") if meta else None,
            )
        )
    return out


async def narrative_cib(db: AsyncSession, narrative_id: int) -> CIBResponse:
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


async def narrative_sentiment_shift(db: AsyncSession, narrative_id: int) -> dict:
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


async def narrative_amplification(db: AsyncSession, narrative_id: int, *, min_posts: int = 2) -> dict:
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
            ).model_dump()
            for c in clusters
        ],
    }


async def build_dashboard_snapshot(db: AsyncSession) -> dict:
    summaries = await list_narrative_summaries(db)
    by_id: dict[str, dict] = {}
    for summary in summaries:
        nid = summary.id
        by_id[str(nid)] = {
            "posts": [p.model_dump(mode="json") for p in await narrative_posts(db, nid)],
            "cib": (await narrative_cib(db, nid)).model_dump(mode="json"),
            "sentiment": await narrative_sentiment_shift(db, nid),
            "amplification": await narrative_amplification(db, nid),
        }

    return {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "narratives": [s.model_dump(mode="json") for s in summaries],
        "by_narrative_id": by_id,
    }
