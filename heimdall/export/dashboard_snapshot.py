"""Build a JSON snapshot for the static analysis dashboard (GitHub Pages)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from heimdall.analysis.duplicates import (
    apply_duplicate_temporal_cib_boost,
    find_duplicate_clusters_from_rows,
)
from heimdall.analysis.sentiment_shift import narrative_sentiment_shift
from heimdall.api.schemas import CIBResponse, DuplicateClusterOut, NarrativeSummary, PostOut
from heimdall.datasets.astroturf import narrative_bot_overlap
from heimdall.datasets.tweet_eval import parse_tweet_eval_meta
from heimdall.config import get_settings
from heimdall.db.models import Narrative, OutrageScore, Platform, Post
from heimdall.graph.export import build_graph_export
from heimdall.nlp.narrative_themes import narrative_theme_clusters
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
    dup_rows = await db.execute(
        select(Post.id, Post.author_id, Post.text, Post.posted_at).where(
            Post.narrative_id == narrative_id
        )
    )
    duplicate_clusters = find_duplicate_clusters_from_rows(list(dup_rows.all()))
    suspicion, signals = apply_duplicate_temporal_cib_boost(
        assessment.suspicion_score,
        assessment.signals,
        duplicate_clusters,
    )
    organic_score = round(1.0 - suspicion, 4)
    bot_overlap = await narrative_bot_overlap(db, narrative_id)
    return CIBResponse(
        narrative_id=narrative_id,
        suspicion_score=round(suspicion, 4),
        organic_score=organic_score,
        signals=signals,
        node_count=m.node_count,
        edge_count=m.edge_count,
        density=m.density,
        top_amplifiers=m.top_amplifiers,
        coordinated_clusters=m.coordinated_clusters,
        iu_astroturf=bot_overlap,
    )


async def narrative_amplification(db: AsyncSession, narrative_id: int, *, min_posts: int = 2) -> dict:
    result = await db.execute(
        select(Post.id, Post.author_id, Post.text, Post.posted_at).where(
            Post.narrative_id == narrative_id
        )
    )
    clusters = find_duplicate_clusters_from_rows(list(result.all()), min_posts=min_posts)
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
                burst_synchronized=c.burst_synchronized,
                burst_author_count=c.burst_author_count,
                cluster_span_seconds=c.cluster_span_seconds,
                min_inter_arrival_seconds=c.min_inter_arrival_seconds,
            ).model_dump()
            for c in clusters
        ],
    }


async def narrative_graph(db: AsyncSession, narrative_id: int) -> dict:
    """Author nodes and propagation edges for the static dashboard graph view."""
    try:
        payload = await build_graph_export(db, narrative_id, include_cib=False)
    except ValueError:
        return {"authors": [], "edges": []}
    return {
        "authors": payload.authors,
        "edges": payload.amplifications,
    }


def _enrich_theme_timelines(clusters: list[dict], post_dates: dict[int, str]) -> None:
    for cluster in clusters:
        dates = sorted(
            {post_dates[pid][:10] for pid in cluster.get("post_ids", []) if pid in post_dates}
        )
        cluster["first_seen"] = dates[0] if dates else None
        cluster["last_seen"] = dates[-1] if dates else None
        cluster["active_days"] = len(dates)


async def narrative_themes(db: AsyncSession, narrative_id: int) -> dict:
    """Embedding theme clusters for static dashboard (mirrors GET /themes)."""
    settings = get_settings()
    if not settings.use_embedding_themes:
        return {
            "available": False,
            "reason": "Set USE_EMBEDDING_THEMES=true and pip install -e '.[ml]' to export themes.",
            "narrative_id": narrative_id,
            "post_count": 0,
            "cluster_count": 0,
            "method": "disabled",
            "model": settings.embedding_model,
            "clusters": [],
            "emerging_theme_count": 0,
        }
    try:
        rows = await db.execute(
            select(Post.id, Post.posted_at).where(Post.narrative_id == narrative_id)
        )
        post_dates = {int(r[0]): r[1].isoformat() for r in rows.all()}
        data = await narrative_theme_clusters(db, narrative_id)
        clusters = data.get("clusters", [])
        _enrich_theme_timelines(clusters, post_dates)
        emerging = [c for c in clusters if c.get("emerging_theme")]
        data["available"] = True
        data["reason"] = None
        data["timeline"] = [
            {
                "cluster_id": c["cluster_id"],
                "label_terms": c.get("label_terms", []),
                "emerging_theme": c.get("emerging_theme", False),
                "size": c.get("size", 0),
                "first_seen": c.get("first_seen"),
                "last_seen": c.get("last_seen"),
                "post_ids": c.get("post_ids", []),
            }
            for c in sorted(
                clusters,
                key=lambda c: (c.get("first_seen") or "9999", -int(c.get("emerging_theme", False))),
            )
        ]
        data["emerging_theme_count"] = len(emerging)
        return data
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
            "narrative_id": narrative_id,
            "post_count": 0,
            "cluster_count": 0,
            "method": "error",
            "model": settings.embedding_model,
            "clusters": [],
            "timeline": [],
            "emerging_theme_count": 0,
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
            "graph": await narrative_graph(db, nid),
            "themes": await narrative_themes(db, nid),
        }

    return {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "narratives": [s.model_dump(mode="json") for s in summaries],
        "by_narrative_id": by_id,
    }
