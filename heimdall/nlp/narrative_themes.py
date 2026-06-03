"""Load narrative posts and cluster themes in embedding space."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from heimdall.analysis.near_duplicates import find_cross_author_fuzzy_clusters
from heimdall.config import get_settings
from heimdall.db.models import Narrative, Post
from heimdall.nlp.embeddings import DEFAULT_EMBEDDING_MODEL
from heimdall.nlp.post_embeddings import load_post_embeddings
from heimdall.nlp.theme_clusters import ThemeClusterReport, cluster_posts, report_to_dict


def _parse_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _must_link_from_fuzzy(rows: list[tuple[int, str, str, str]]) -> list[list[int]]:
    clusters = find_cross_author_fuzzy_clusters(rows)
    return [list(cluster.post_ids) for cluster in clusters if len(cluster.post_ids) >= 2]


async def _load_narrative_cluster_inputs(
    session: AsyncSession,
    narrative_id: int,
) -> tuple[
    list[tuple[int, str, str]],
    dict[int, str],
    list[str],
    list[list[int]],
    dict[int, object],
    str,
]:
    result = await session.execute(
        select(Post.id, Post.text, Post.author_id, Post.posted_at)
        .where(Post.narrative_id == narrative_id)
        .order_by(Post.posted_at)
    )
    rows_raw = result.all()
    rows = [(int(r[0]), str(r[1]), str(r[2])) for r in rows_raw]
    post_dates = {int(r[0]): r[3].isoformat() for r in rows_raw}

    narrative = await session.get(Narrative, narrative_id)
    keywords = _parse_keywords(narrative.keywords if narrative else None)

    fuzzy_rows = [
        (int(r[0]), str(r[2]), str(r[1]), post_dates[int(r[0])][:10]) for r in rows_raw
    ]
    must_link_groups = _must_link_from_fuzzy(fuzzy_rows)

    settings = get_settings()
    model_name = settings.embedding_model or DEFAULT_EMBEDDING_MODEL
    post_ids = [pid for pid, _, _ in rows]
    cached = await load_post_embeddings(session, post_ids, model_name=model_name)
    return rows, post_dates, keywords, must_link_groups, cached, model_name


async def narrative_theme_clusters(
    session: AsyncSession,
    narrative_id: int,
) -> dict:
    rows, post_dates, keywords, must_link_groups, cached, model_name = await _load_narrative_cluster_inputs(
        session, narrative_id
    )
    report = cluster_posts(
        rows,
        narrative_id=narrative_id,
        model_name=model_name,
        cached_embeddings=cached,
        must_link_groups=must_link_groups,
        narrative_keywords=keywords,
        post_dates=post_dates,
    )
    return report_to_dict(report)


async def narrative_theme_report(
    session: AsyncSession,
    narrative_id: int,
) -> ThemeClusterReport:
    rows, post_dates, keywords, must_link_groups, cached, model_name = await _load_narrative_cluster_inputs(
        session, narrative_id
    )
    return cluster_posts(
        rows,
        narrative_id=narrative_id,
        model_name=model_name,
        cached_embeddings=cached,
        must_link_groups=must_link_groups,
        narrative_keywords=keywords,
        post_dates=post_dates,
    )
