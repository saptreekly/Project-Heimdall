"""Build a JSON snapshot for the static analysis dashboard (GitHub Pages)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from heimdall.analysis.cib_report import build_cib_report
from heimdall.analysis.duplicates import find_duplicate_clusters_from_rows
from heimdall.analysis.near_duplicates import (
    author_spam_summaries,
    copypasta_scores,
    find_cross_author_fuzzy_clusters,
    find_near_duplicate_groups,
    jaccard_threshold_config,
    post_id_to_cross_author_cluster,
    post_id_to_near_group,
    resolve_jaccard_threshold,
)
from heimdall.export.cross_pollination_loader import load_cross_pollination, per_narrative_hits
from heimdall.export.provenance import SNAPSHOT_POST_LIMIT, build_narrative_provenance
from heimdall.export.post_meta import parse_x_screen_name, post_status_url
from heimdall.analysis.sentiment_shift import narrative_sentiment_shift
from heimdall.api.schemas import CIBResponse, DuplicateClusterOut, NarrativeSummary, PostOut
from heimdall.datasets.tweet_eval import parse_tweet_eval_meta
from heimdall.config import get_settings
from heimdall.db.models import Narrative, OutrageScore, Platform, Post
from heimdall.graph.export import build_graph_export
from heimdall.graph.stats import build_graph_stats
from heimdall.nlp.narrative_themes import narrative_theme_clusters


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


async def _narrative_post_rows(
    db: AsyncSession, narrative_id: int, *, limit: int = SNAPSHOT_POST_LIMIT
) -> list[tuple]:
    rows = await db.execute(
        select(
            Post.id,
            cast(Post.platform, String),
            Post.external_id,
            Post.author_id,
            Post.text,
            Post.posted_at,
            Post.raw_json,
        )
        .where(Post.narrative_id == narrative_id)
        .order_by(Post.posted_at.desc())
        .limit(limit)
    )
    return list(rows.all())


async def narrative_posts(db: AsyncSession, narrative_id: int) -> list[PostOut]:
    raw_rows = await _narrative_post_rows(db, narrative_id)
    jaccard_th, _, _, _ = resolve_jaccard_threshold()
    near_input = [
        (pid, author_id, text, posted_at.isoformat())
        for pid, _plat, _ext, author_id, text, posted_at, _raw in raw_rows
    ]
    near_groups = find_near_duplicate_groups(near_input, threshold=jaccard_th)
    cross_fuzzy = find_cross_author_fuzzy_clusters(near_input, threshold=jaccard_th)
    near_map = post_id_to_near_group(near_groups)
    cross_map = post_id_to_cross_author_cluster(cross_fuzzy)
    copy_rows = [(pid, author_id, text) for pid, _p, _e, author_id, text, _t, _r in raw_rows]
    pasta_scores = copypasta_scores(copy_rows)

    out: list[PostOut] = []
    for pid, platform_raw, external_id, author_id, text, posted_at, raw_json in raw_rows:
        score_row = await db.execute(
            select(OutrageScore.outrage_index, OutrageScore.sentiment_label).where(
                OutrageScore.post_id == pid
            )
        )
        score = score_row.first()
        meta = parse_tweet_eval_meta(raw_json)
        platform = _normalize_platform(platform_raw)
        handle = parse_x_screen_name(raw_json)
        out.append(
            PostOut(
                id=pid,
                platform=platform,
                external_id=external_id,
                author_id=author_id,
                author_handle=handle,
                text=text,
                posted_at=posted_at,
                outrage_index=score[0] if score else None,
                sentiment_label=score[1] if score else None,
                benchmark_label=meta.get("label_name") if meta else None,
                near_duplicate_group=near_map.get(pid),
                cross_author_fuzzy_cluster=cross_map.get(pid),
                copypasta_score=pasta_scores.get(pid),
                status_url=post_status_url(platform, external_id),
            )
        )
    return out


async def narrative_near_duplicates(db: AsyncSession, narrative_id: int) -> dict:
    raw_rows = await _narrative_post_rows(db, narrative_id)
    jaccard_th, th_min, th_max, th_step = resolve_jaccard_threshold()
    near_input = [
        (pid, author_id, text, posted_at.isoformat())
        for pid, _plat, _ext, author_id, text, posted_at, _raw in raw_rows
    ]
    groups = find_near_duplicate_groups(near_input, threshold=jaccard_th)
    cross_fuzzy = find_cross_author_fuzzy_clusters(near_input, threshold=jaccard_th)
    return {
        **jaccard_threshold_config(
            jaccard_th,
            threshold_min=th_min,
            threshold_max=th_max,
            threshold_step=th_step,
        ),
        "same_author_group_count": len(groups),
        "group_count": len(groups),
        "groups": [
            {
                "group_id": g.group_id,
                "author_id": g.author_id,
                "post_ids": g.post_ids,
                "count": g.count,
                "sample_text": g.sample_text,
                "max_similarity": round(g.max_similarity, 4),
            }
            for g in groups
        ],
        "cross_author_fuzzy_count": len(cross_fuzzy),
        "cross_author_fuzzy": [
            {
                "cluster_id": c.cluster_id,
                "post_ids": c.post_ids,
                "author_ids": c.author_ids,
                "author_count": c.author_count,
                "count": c.count,
                "sample_text": c.sample_text,
                "max_similarity": c.max_similarity,
                "burst_synchronized": c.burst_synchronized,
                "burst_author_count": c.burst_author_count,
                "cluster_span_seconds": c.cluster_span_seconds,
                "min_inter_arrival_seconds": c.min_inter_arrival_seconds,
            }
            for c in cross_fuzzy
        ],
        "author_summaries": author_spam_summaries(near_input, near_groups=groups),
    }


def _benchmark_stats(posts: list[PostOut]) -> dict | None:
    labeled = [p for p in posts if p.benchmark_label]
    if not labeled:
        return None
    return {
        "labeled_posts": len(labeled),
        "total_posts": len(posts),
        "labels": sorted({p.benchmark_label for p in labeled if p.benchmark_label}),
    }


def _load_x_rate_state() -> dict | None:
    path = Path(__file__).resolve().parents[2] / "data" / "dashboard" / "x_rate_state.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


async def narrative_cib(
    db: AsyncSession,
    narrative_id: int,
    *,
    cross_pollination_report: dict | None = None,
    graph_stats: dict | None = None,
) -> CIBResponse:
    return await build_cib_report(
        db,
        narrative_id,
        cross_pollination_report=cross_pollination_report,
        graph_stats=graph_stats,
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
        return {
            "authors": [],
            "edges": [],
            "stats": build_graph_stats([], []),
        }
    authors = payload.authors
    edges = payload.amplifications

    return {
        "authors": authors,
        "edges": edges,
        "stats": build_graph_stats(authors, edges),
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
            "reason": "Set USE_EMBEDDING_THEMES=true when exporting snapshot.json (CI does this automatically).",
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
                "label_distinctiveness": c.get("label_distinctiveness", 0.0),
                "emerging_theme": c.get("emerging_theme", False),
                "size": c.get("size", 0),
                "first_seen": c.get("first_seen"),
                "last_seen": c.get("last_seen"),
                "post_ids": c.get("post_ids", []),
            }
            for c in sorted(
                (
                    c
                    for c in clusters
                    if float(c.get("label_distinctiveness", 0.0)) >= 0.12
                    or c.get("emerging_theme")
                ),
                key=lambda c: (
                    c.get("first_seen") or "9999",
                    -float(c.get("label_distinctiveness", 0.0)),
                    -int(c.get("emerging_theme", False)),
                ),
            )
        ]
        data["distinct_theme_count"] = data.get(
            "distinct_theme_count",
            sum(1 for c in clusters if float(c.get("label_distinctiveness", 0.0)) >= 0.12),
        )
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
    cross_pollination = await load_cross_pollination(db)
    by_id: dict[str, dict] = {}
    for summary in summaries:
        nid = summary.id
        raw_rows = await _narrative_post_rows(db, nid)
        snapshot_post_ids = [row[0] for row in raw_rows]
        posts = await narrative_posts(db, nid)
        graph = await narrative_graph(db, nid)
        amp = await narrative_amplification(db, nid)
        near_dup = await narrative_near_duplicates(db, nid)
        themes = await narrative_themes(db, nid)
        cib = await narrative_cib(
            db,
            nid,
            cross_pollination_report=cross_pollination,
            graph_stats=graph.get("stats"),
        )
        by_id[str(nid)] = {
            "posts": [p.model_dump(mode="json") for p in posts],
            "cib": cib.model_dump(mode="json"),
            "sentiment": await narrative_sentiment_shift(db, nid, post_ids=snapshot_post_ids),
            "amplification": amp,
            "near_duplicates": near_dup,
            "cross_pollination_hits": per_narrative_hits(cross_pollination, nid),
            "graph": graph,
            "themes": themes,
            "benchmark": _benchmark_stats(posts),
            "provenance": build_narrative_provenance(
                posts_total_db=summary.post_count,
                posts_in_snapshot=[p.model_dump(mode="json") for p in posts],
                graph_stats=graph.get("stats", {}),
                themes=themes,
                duplicate_cluster_count=amp.get("cluster_count", 0),
                fuzzy_cluster_count=near_dup.get("cross_author_fuzzy_count", 0),
            ),
        }

    return {
        "version": 5,
        "generated_at": datetime.now(UTC).isoformat(),
        "narratives": [s.model_dump(mode="json") for s in summaries],
        "by_narrative_id": by_id,
        "cross_pollination": cross_pollination,
        "meta": {
            "ingest_workflow_url": "https://github.com/saptreekly/Project-Heimdall/actions/workflows/ingest.yml",
            "pages_workflow_url": "https://github.com/saptreekly/Project-Heimdall/actions/workflows/pages.yml",
            "x_rate": _load_x_rate_state(),
        },
    }
